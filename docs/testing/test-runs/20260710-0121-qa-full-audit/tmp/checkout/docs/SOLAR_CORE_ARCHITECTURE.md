# Solar Core Architecture

> 版本: 3.0 | 日期: 2026-01-29 | 状态: 设计中

## 一、系统全景

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Solar v3.0 Architecture                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│    ┌─────────────────────────────────────────────────────────────────┐     │
│    │                    🧠 Brain Layer (LLM)                         │     │
│    │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │     │
│    │  │ Claude  │ │ OpenAI  │ │ Gemini  │ │Deepseek │ │  GLM    │   │     │
│    │  │ (Opus)  │ │ (GPT-4) │ │ (Pro)   │ │  (V3)   │ │ (GLM-4) │   │     │
│    │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │     │
│    │       └───────────┴───────────┼───────────┴───────────┘        │     │
│    │                               ▼                                 │     │
│    │              ┌─────────────────────────────────┐               │     │
│    │              │      Model Router/Adapter       │               │     │
│    │              └─────────────────────────────────┘               │     │
│    └──────────────────────────────┬──────────────────────────────────┘     │
│                                   │                                         │
│    ┌──────────────────────────────┼──────────────────────────────────┐     │
│    │                    ❤️ Heart Layer (Daemon)                      │     │
│    │                              │                                  │     │
│    │  ┌───────────────────────────┴───────────────────────────────┐ │     │
│    │  │                    Solar Daemon                           │ │     │
│    │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │ │     │
│    │  │  │Scheduler │ │ Message  │ │ Workflow │ │  Agent   │     │ │     │
│    │  │  │ (Cron)   │ │  Queue   │ │  Engine  │ │ Dispatch │     │ │     │
│    │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │ │     │
│    │  └───────────────────────────────────────────────────────────┘ │     │
│    └──────────────────────────────┬──────────────────────────────────┘     │
│                                   │                                         │
│    ┌──────────────────────────────┼──────────────────────────────────┐     │
│    │                   🧬 Nerve Layer (SQLite)                       │     │
│    │                              │                                  │     │
│    │  ┌───────────────────────────┴───────────────────────────────┐ │     │
│    │  │                    solar.db                               │ │     │
│    │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │ │     │
│    │  │  │  Tasks   │ │ Messages │ │  State   │ │  Agents  │     │ │     │
│    │  │  │  Table   │ │  Table   │ │  Table   │ │  Table   │     │ │     │
│    │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │ │     │
│    │  └───────────────────────────────────────────────────────────┘ │     │
│    └──────────────────────────────┬──────────────────────────────────┘     │
│                                   │                                         │
│    ┌──────────────────────────────┼──────────────────────────────────┐     │
│    │                   🔌 Plugin Layer                                │     │
│    │                              │                                  │     │
│    │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │     │
│    │  │  Skills  │ │  Hooks   │ │  Agents  │ │  Custom  │           │     │
│    │  │ (内置)   │ │ (事件)   │ │ (角色)   │ │ (用户)   │           │     │
│    │  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │     │
│    └─────────────────────────────────────────────────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 二、核心隐喻

| 层级 | 隐喻 | 组件 | 职责 |
|------|------|------|------|
| **Brain** | 🧠 脑 | LLM 多模型 | 思考、决策、生成 |
| **Heart** | ❤️ 心脏 | Daemon | 驱动、调度、循环 |
| **Nerve** | 🧬 神经 | SQLite | 状态、记忆、传导 |
| **Plugin** | 🔌 器官 | 插件系统 | 能力、扩展、适配 |

---

## 三、❤️ Heart Layer - Daemon 设计

### 3.1 职责

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Solar Daemon                                 │
│                    "The Beating Heart"                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                     Core Functions                            │  │
│  ├───────────────────────────────────────────────────────────────┤  │
│  │                                                               │  │
│  │  1. 🔄 Workflow Engine                                        │  │
│  │     - 驱动五阶段流程 (P1→P2→P3→P4→P5)                        │  │
│  │     - 管理 Gate 检查点                                        │  │
│  │     - 协调 Agent 切换                                         │  │
│  │                                                               │  │
│  │  2. 📨 Message Queue                                          │  │
│  │     - 收集系统消息 (Hook 产生)                                │  │
│  │     - 定时写入 SQLite                                         │  │
│  │     - 消息路由分发                                            │  │
│  │                                                               │  │
│  │  3. ⏰ Scheduler                                               │  │
│  │     - 定时任务 (缓存清理、状态同步)                           │  │
│  │     - Cron-like 调度                                          │  │
│  │     - 后台任务队列                                            │  │
│  │                                                               │  │
│  │  4. 🤖 Agent Dispatcher                                       │  │
│  │     - Agent 生命周期管理                                      │  │
│  │     - Agent 间通信                                            │  │
│  │     - 并行 Agent 协调                                         │  │
│  │                                                               │  │
│  │  5. 🔌 Plugin Host                                            │  │
│  │     - 加载/卸载插件                                           │  │
│  │     - 插件生命周期                                            │  │
│  │     - 插件间通信                                              │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Daemon 实现

```typescript
// daemon/server.ts

import { Database } from 'bun:sqlite';
import { watch } from 'fs';

interface DaemonConfig {
  socketPath: string;        // /tmp/solar.sock
  dbPath: string;            // ~/.solar/solar.db
  cacheDir: string;          // ~/.solar/cache
  pluginDir: string;         // ~/.solar/plugins
  syncInterval: number;      // 消息同步间隔 (ms)
}

export class SolarDaemon {
  private db: Database;
  private messageQueue: Message[] = [];
  private scheduler: Scheduler;
  private pluginHost: PluginHost;
  private workflowEngine: WorkflowEngine;
  private agentDispatcher: AgentDispatcher;

  constructor(config: DaemonConfig) {
    // 初始化数据库连接
    this.db = new Database(config.dbPath);
    this.initDatabase();

    // 初始化各子系统
    this.scheduler = new Scheduler();
    this.pluginHost = new PluginHost(config.pluginDir);
    this.workflowEngine = new WorkflowEngine(this.db);
    this.agentDispatcher = new AgentDispatcher(this.db);

    // 启动定时任务
    this.startScheduledTasks(config);

    // 启动文件监听
    this.startFileWatcher(config.cacheDir);
  }

  // ==================== 心跳循环 ====================

  private startScheduledTasks(config: DaemonConfig) {
    // 消息同步 - 每秒
    this.scheduler.every(config.syncInterval, async () => {
      await this.syncMessages();
    });

    // 状态检查 - 每 5 秒
    this.scheduler.every(5000, async () => {
      await this.checkWorkflowState();
    });

    // 缓存清理 - 每小时
    this.scheduler.every(3600000, async () => {
      await this.cleanupCache();
    });

    // 插件健康检查 - 每分钟
    this.scheduler.every(60000, async () => {
      await this.pluginHost.healthCheck();
    });
  }

  // ==================== 消息队列 ====================

  async enqueueMessage(msg: Message) {
    this.messageQueue.push(msg);
  }

  private async syncMessages() {
    if (this.messageQueue.length === 0) return;

    const batch = this.messageQueue.splice(0, 100); // 批量处理
    const stmt = this.db.prepare(`
      INSERT INTO messages (type, source, content, timestamp)
      VALUES (?, ?, ?, ?)
    `);

    this.db.transaction(() => {
      for (const msg of batch) {
        stmt.run(msg.type, msg.source, JSON.stringify(msg.content), msg.timestamp);
      }
    })();
  }

  // ==================== 文件监听 ====================

  private startFileWatcher(cacheDir: string) {
    // 监听缓存目录的消息文件
    watch(cacheDir, { recursive: true }, async (event, filename) => {
      if (filename?.endsWith('.msg.json')) {
        const content = await Bun.file(`${cacheDir}/${filename}`).json();
        await this.enqueueMessage(content);
        // 处理后删除
        await Bun.file(`${cacheDir}/${filename}`).delete();
      }
    });
  }

  // ==================== 工作流驱动 ====================

  private async checkWorkflowState() {
    const activeFlows = await this.workflowEngine.getActiveFlows();

    for (const flow of activeFlows) {
      // 检查 Gate 条件
      if (await this.workflowEngine.shouldTransition(flow)) {
        await this.workflowEngine.transition(flow);
        await this.agentDispatcher.switchAgent(flow.nextAgent);
      }

      // 检查超时
      if (this.workflowEngine.isStale(flow)) {
        await this.notifyStaleFlow(flow);
      }
    }
  }

  // ==================== Unix Socket 服务 ====================

  async startServer(socketPath: string) {
    Bun.serve({
      unix: socketPath,
      fetch: async (req) => {
        const url = new URL(req.url);
        const path = url.pathname;

        switch (path) {
          case '/status':
            return Response.json(await this.getStatus());
          case '/workflow/start':
            return Response.json(await this.workflowEngine.start(await req.json()));
          case '/workflow/transition':
            return Response.json(await this.workflowEngine.manualTransition(await req.json()));
          case '/agent/dispatch':
            return Response.json(await this.agentDispatcher.dispatch(await req.json()));
          case '/message/send':
            await this.enqueueMessage(await req.json());
            return Response.json({ ok: true });
          case '/plugin/load':
            return Response.json(await this.pluginHost.load(await req.json()));
          case '/render':
            return Response.json(await this.render(await req.json()));
          default:
            return new Response('Not Found', { status: 404 });
        }
      }
    });

    console.log(`Solar Daemon listening on ${socketPath}`);
  }
}
```

### 3.3 启动脚本

```bash
#!/bin/bash
# ~/.claude/solar/bin/solar-daemon

SOCKET_PATH="/tmp/solar.sock"
PID_FILE="$HOME/.solar/daemon.pid"
LOG_FILE="$HOME/.solar/daemon.log"

case "$1" in
  start)
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
      echo "Daemon already running"
      exit 1
    fi
    nohup bun run ~/.claude/solar/daemon/server.ts > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Daemon started (PID: $(cat $PID_FILE))"
    ;;
  stop)
    if [ -f "$PID_FILE" ]; then
      kill $(cat "$PID_FILE") 2>/dev/null
      rm -f "$PID_FILE" "$SOCKET_PATH"
      echo "Daemon stopped"
    fi
    ;;
  status)
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
      echo "Daemon running (PID: $(cat $PID_FILE))"
    else
      echo "Daemon not running"
    fi
    ;;
  *)
    echo "Usage: $0 {start|stop|status}"
    ;;
esac
```

---

## 四、🧬 Nerve Layer - SQLite 设计

### 4.1 数据库 Schema

```sql
-- ~/.solar/solar.db

-- ==================== 核心表 ====================

-- 任务表
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    description TEXT NOT NULL,
    complexity TEXT CHECK(complexity IN ('simple', 'medium', 'complex')),
    status TEXT CHECK(status IN ('pending', 'in_progress', 'completed', 'failed')),
    current_phase TEXT,
    current_agent TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    metadata JSON
);

-- 消息表 (系统事件日志)
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,           -- 'hook', 'agent', 'workflow', 'plugin', 'error'
    source TEXT NOT NULL,         -- 来源组件
    content JSON NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE
);

-- 状态表 (实时状态快照)
CREATE TABLE state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,     -- 'flow.current_phase', 'agent.active', etc.
    value JSON NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Agent 执行记录
CREATE TABLE agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id),
    agent TEXT NOT NULL,
    phase TEXT NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    status TEXT CHECK(status IN ('running', 'success', 'failed', 'timeout')),
    input JSON,
    output JSON,
    tokens_used INTEGER,
    model_used TEXT
);

-- 工作流转换历史
CREATE TABLE workflow_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id),
    from_phase TEXT,
    to_phase TEXT,
    from_agent TEXT,
    to_agent TEXT,
    gate_passed TEXT,             -- 'G1', 'G2', 'G3', NULL
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    metadata JSON
);

-- 插件注册表
CREATE TABLE plugins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    version TEXT NOT NULL,
    type TEXT CHECK(type IN ('skill', 'hook', 'agent', 'model', 'custom')),
    path TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    config JSON,
    installed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Token 使用统计
CREATE TABLE token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    UNIQUE(date, model)
);

-- 会话历史
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    summary TEXT,
    checkpoint JSON              -- 可恢复的状态快照
);

-- ==================== 索引 ====================

CREATE INDEX idx_tasks_project ON tasks(project);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_messages_type ON messages(type);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);
CREATE INDEX idx_agent_runs_task ON agent_runs(task_id);
CREATE INDEX idx_token_usage_date ON token_usage(date);
```

### 4.2 状态管理器

```typescript
// nerve/state-manager.ts

import { Database } from 'bun:sqlite';

export class StateManager {
  private db: Database;
  private cache: Map<string, any> = new Map();

  constructor(db: Database) {
    this.db = db;
    this.loadCache();
  }

  private loadCache() {
    const rows = this.db.query('SELECT key, value FROM state').all();
    for (const row of rows as any[]) {
      this.cache.set(row.key, JSON.parse(row.value));
    }
  }

  // 获取状态 (优先从缓存)
  get<T>(key: string, defaultValue?: T): T | undefined {
    if (this.cache.has(key)) {
      return this.cache.get(key) as T;
    }
    return defaultValue;
  }

  // 设置状态 (同时更新缓存和数据库)
  set(key: string, value: any) {
    this.cache.set(key, value);
    this.db.run(`
      INSERT INTO state (key, value, updated_at)
      VALUES (?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(key) DO UPDATE SET
        value = excluded.value,
        updated_at = CURRENT_TIMESTAMP
    `, [key, JSON.stringify(value)]);
  }

  // 批量获取
  getMany(prefix: string): Record<string, any> {
    const result: Record<string, any> = {};
    for (const [key, value] of this.cache) {
      if (key.startsWith(prefix)) {
        result[key] = value;
      }
    }
    return result;
  }

  // 订阅变更 (观察者模式)
  private listeners: Map<string, Set<(value: any) => void>> = new Map();

  subscribe(key: string, callback: (value: any) => void) {
    if (!this.listeners.has(key)) {
      this.listeners.set(key, new Set());
    }
    this.listeners.get(key)!.add(callback);
    return () => this.listeners.get(key)?.delete(callback);
  }

  private notify(key: string, value: any) {
    this.listeners.get(key)?.forEach(cb => cb(value));
    // 通配符订阅
    this.listeners.get('*')?.forEach(cb => cb({ key, value }));
  }
}
```

### 4.3 查询接口

```typescript
// nerve/queries.ts

export class SolarQueries {
  constructor(private db: Database) {}

  // 获取当前活跃任务
  getActiveTasks(project?: string) {
    const sql = project
      ? `SELECT * FROM tasks WHERE status = 'in_progress' AND project = ?`
      : `SELECT * FROM tasks WHERE status = 'in_progress'`;
    return this.db.query(sql).all(project ? [project] : []);
  }

  // 获取 Token 使用统计
  getTokenUsage(days: number = 7) {
    return this.db.query(`
      SELECT date, model, SUM(input_tokens) as input, SUM(output_tokens) as output, SUM(cost_usd) as cost
      FROM token_usage
      WHERE date >= date('now', '-' || ? || ' days')
      GROUP BY date, model
      ORDER BY date DESC
    `).all([days]);
  }

  // 获取 Agent 执行统计
  getAgentStats(taskId?: number) {
    const where = taskId ? 'WHERE task_id = ?' : '';
    return this.db.query(`
      SELECT agent, COUNT(*) as runs, AVG(tokens_used) as avg_tokens,
             SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count
      FROM agent_runs
      ${where}
      GROUP BY agent
    `).all(taskId ? [taskId] : []);
  }

  // 获取最近消息
  getRecentMessages(limit: number = 50, type?: string) {
    const where = type ? 'WHERE type = ?' : '';
    return this.db.query(`
      SELECT * FROM messages ${where}
      ORDER BY timestamp DESC LIMIT ?
    `).all(type ? [type, limit] : [limit]);
  }

  // 获取工作流历史
  getWorkflowHistory(taskId: number) {
    return this.db.query(`
      SELECT * FROM workflow_transitions
      WHERE task_id = ?
      ORDER BY timestamp ASC
    `).all([taskId]);
  }
}
```

---

## 五、🧠 Brain Layer - 多模型适配

### 5.1 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Model Adapter Layer                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    ModelRouter                                │  │
│  │                                                               │  │
│  │  任务复杂度   ──────▶  模型选择策略  ──────▶  适配器调用      │  │
│  │                                                               │  │
│  │  - simple    ──────▶  Haiku/GLM-Flash                        │  │
│  │  - medium    ──────▶  Sonnet/GPT-4o-mini/Deepseek            │  │
│  │  - complex   ──────▶  Opus/GPT-4/Gemini-Pro                  │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│         ┌────────────────────┼────────────────────┐                │
│         │                    │                    │                │
│         ▼                    ▼                    ▼                │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐        │
│  │   Claude    │      │   OpenAI    │      │   Others    │        │
│  │   Adapter   │      │   Adapter   │      │   Adapter   │        │
│  └─────────────┘      └─────────────┘      └─────────────┘        │
│         │                    │                    │                │
│         ▼                    ▼                    ▼                │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐        │
│  │ Anthropic   │      │  OpenAI     │      │  各厂商     │        │
│  │    API      │      │    API      │      │    API      │        │
│  └─────────────┘      └─────────────┘      └─────────────┘        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 配置文件

```bash
# ~/.solar/.env

# ==================== Claude ====================
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_DEFAULT_MODEL=claude-sonnet-4-20250514

# ==================== OpenAI ====================
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_DEFAULT_MODEL=gpt-4o

# ==================== Gemini ====================
GOOGLE_API_KEY=...
GEMINI_DEFAULT_MODEL=gemini-1.5-pro

# ==================== Deepseek ====================
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_DEFAULT_MODEL=deepseek-chat

# ==================== GLM (智谱) ====================
GLM_API_KEY=...
GLM_DEFAULT_MODEL=glm-4-flash

# ==================== Minimax ====================
MINIMAX_API_KEY=...
MINIMAX_GROUP_ID=...
MINIMAX_DEFAULT_MODEL=abab6.5-chat

# ==================== 路由策略 ====================
# 任务复杂度 -> 模型映射
MODEL_ROUTE_SIMPLE=glm-4-flash
MODEL_ROUTE_MEDIUM=deepseek-chat
MODEL_ROUTE_COMPLEX=claude-opus-4-5-20251101

# 成本控制
DAILY_BUDGET_USD=10.0
PREFER_CHEAP_MODEL=true
```

### 5.3 统一接口

```typescript
// brain/types.ts

export interface Message {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface CompletionRequest {
  messages: Message[];
  model?: string;
  temperature?: number;
  maxTokens?: number;
  tools?: Tool[];
  stream?: boolean;
}

export interface CompletionResponse {
  content: string;
  model: string;
  usage: {
    inputTokens: number;
    outputTokens: number;
  };
  toolCalls?: ToolCall[];
  finishReason: 'stop' | 'tool_use' | 'length' | 'error';
}

export interface ModelAdapter {
  name: string;
  models: string[];
  complete(req: CompletionRequest): Promise<CompletionResponse>;
  stream(req: CompletionRequest): AsyncGenerator<string>;
  isAvailable(): Promise<boolean>;
  estimateCost(inputTokens: number, outputTokens: number, model: string): number;
}
```

### 5.4 适配器实现

```typescript
// brain/adapters/claude.ts

import Anthropic from '@anthropic-ai/sdk';

export class ClaudeAdapter implements ModelAdapter {
  name = 'claude';
  models = ['claude-opus-4-5-20251101', 'claude-sonnet-4-20250514', 'claude-haiku-3-5-20241022'];

  private client: Anthropic;

  constructor() {
    this.client = new Anthropic({
      apiKey: process.env.ANTHROPIC_API_KEY
    });
  }

  async complete(req: CompletionRequest): Promise<CompletionResponse> {
    const response = await this.client.messages.create({
      model: req.model || 'claude-sonnet-4-20250514',
      max_tokens: req.maxTokens || 4096,
      messages: req.messages.map(m => ({
        role: m.role === 'system' ? 'user' : m.role,
        content: m.content
      })),
      system: req.messages.find(m => m.role === 'system')?.content
    });

    return {
      content: response.content[0].type === 'text' ? response.content[0].text : '',
      model: response.model,
      usage: {
        inputTokens: response.usage.input_tokens,
        outputTokens: response.usage.output_tokens
      },
      finishReason: response.stop_reason === 'end_turn' ? 'stop' : 'stop'
    };
  }

  estimateCost(input: number, output: number, model: string): number {
    const pricing: Record<string, [number, number]> = {
      'claude-opus-4-5-20251101': [15, 75],      // per 1M tokens
      'claude-sonnet-4-20250514': [3, 15],
      'claude-haiku-3-5-20241022': [0.25, 1.25]
    };
    const [inPrice, outPrice] = pricing[model] || [3, 15];
    return (input * inPrice + output * outPrice) / 1_000_000;
  }
}

// brain/adapters/openai.ts

import OpenAI from 'openai';

export class OpenAIAdapter implements ModelAdapter {
  name = 'openai';
  models = ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'o1', 'o1-mini'];

  private client: OpenAI;

  constructor() {
    this.client = new OpenAI({
      apiKey: process.env.OPENAI_API_KEY,
      baseURL: process.env.OPENAI_BASE_URL
    });
  }

  async complete(req: CompletionRequest): Promise<CompletionResponse> {
    const response = await this.client.chat.completions.create({
      model: req.model || 'gpt-4o',
      messages: req.messages,
      max_tokens: req.maxTokens,
      temperature: req.temperature
    });

    const choice = response.choices[0];
    return {
      content: choice.message.content || '',
      model: response.model,
      usage: {
        inputTokens: response.usage?.prompt_tokens || 0,
        outputTokens: response.usage?.completion_tokens || 0
      },
      finishReason: choice.finish_reason === 'stop' ? 'stop' : 'stop'
    };
  }

  estimateCost(input: number, output: number, model: string): number {
    const pricing: Record<string, [number, number]> = {
      'gpt-4o': [2.5, 10],
      'gpt-4o-mini': [0.15, 0.6],
      'gpt-4-turbo': [10, 30],
      'o1': [15, 60],
      'o1-mini': [3, 12]
    };
    const [inPrice, outPrice] = pricing[model] || [2.5, 10];
    return (input * inPrice + output * outPrice) / 1_000_000;
  }
}

// brain/adapters/deepseek.ts

export class DeepseekAdapter implements ModelAdapter {
  name = 'deepseek';
  models = ['deepseek-chat', 'deepseek-coder', 'deepseek-reasoner'];

  private client: OpenAI; // OpenAI 兼容接口

  constructor() {
    this.client = new OpenAI({
      apiKey: process.env.DEEPSEEK_API_KEY,
      baseURL: process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com/v1'
    });
  }

  // ... 实现类似 OpenAI

  estimateCost(input: number, output: number, model: string): number {
    // Deepseek 价格很低
    return (input * 0.14 + output * 0.28) / 1_000_000;
  }
}
```

### 5.5 模型路由器

```typescript
// brain/router.ts

export class ModelRouter {
  private adapters: Map<string, ModelAdapter> = new Map();
  private modelToAdapter: Map<string, string> = new Map();
  private stateManager: StateManager;

  constructor(stateManager: StateManager) {
    this.stateManager = stateManager;
    this.registerAdapters();
  }

  private registerAdapters() {
    const adapters = [
      new ClaudeAdapter(),
      new OpenAIAdapter(),
      new DeepseekAdapter(),
      new GeminiAdapter(),
      new GLMAdapter(),
      new MinimaxAdapter()
    ];

    for (const adapter of adapters) {
      this.adapters.set(adapter.name, adapter);
      for (const model of adapter.models) {
        this.modelToAdapter.set(model, adapter.name);
      }
    }
  }

  // 根据任务复杂度选择模型
  selectModel(complexity: 'simple' | 'medium' | 'complex'): string {
    const routes = {
      simple: process.env.MODEL_ROUTE_SIMPLE || 'claude-haiku-3-5-20241022',
      medium: process.env.MODEL_ROUTE_MEDIUM || 'claude-sonnet-4-20250514',
      complex: process.env.MODEL_ROUTE_COMPLEX || 'claude-opus-4-5-20251101'
    };

    // 检查预算
    if (this.isOverBudget()) {
      return this.getCheapestModel();
    }

    return routes[complexity];
  }

  // 执行请求
  async complete(req: CompletionRequest): Promise<CompletionResponse> {
    const model = req.model || this.selectModel('medium');
    const adapterName = this.modelToAdapter.get(model);

    if (!adapterName) {
      throw new Error(`Unknown model: ${model}`);
    }

    const adapter = this.adapters.get(adapterName)!;

    // 检查可用性
    if (!await adapter.isAvailable()) {
      // 回退到备用模型
      return this.fallback(req);
    }

    const response = await adapter.complete({ ...req, model });

    // 记录使用
    await this.recordUsage(model, response.usage);

    return response;
  }

  private async recordUsage(model: string, usage: { inputTokens: number; outputTokens: number }) {
    const adapter = this.adapters.get(this.modelToAdapter.get(model)!)!;
    const cost = adapter.estimateCost(usage.inputTokens, usage.outputTokens, model);

    // 写入数据库
    // ... INSERT INTO token_usage
  }

  private isOverBudget(): boolean {
    const dailyBudget = parseFloat(process.env.DAILY_BUDGET_USD || '10');
    const todayUsage = this.stateManager.get<number>('token_usage.today_cost') || 0;
    return todayUsage >= dailyBudget;
  }

  private getCheapestModel(): string {
    // Deepseek 最便宜
    return 'deepseek-chat';
  }
}
```

---

## 六、🔌 Plugin Layer - 插件系统

### 6.1 插件类型

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Plugin System                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      Plugin Types                            │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │                                                             │   │
│  │  📁 Skill Plugin                                            │   │
│  │  ├── 用户可调用的命令 (/commit, /pr, /test)                 │   │
│  │  └── SKILL.md + 可选脚本                                    │   │
│  │                                                             │   │
│  │  🪝 Hook Plugin                                              │   │
│  │  ├── 事件拦截器 (PreToolUse, PostToolUse, Stop)             │   │
│  │  └── .sh 或 .ts 脚本                                        │   │
│  │                                                             │   │
│  │  🤖 Agent Plugin                                             │   │
│  │  ├── 自定义 Agent 角色                                      │   │
│  │  └── agent.md + 配置                                        │   │
│  │                                                             │   │
│  │  🧠 Model Plugin                                             │   │
│  │  ├── 新模型适配器                                           │   │
│  │  └── adapter.ts                                             │   │
│  │                                                             │   │
│  │  🔧 Custom Plugin                                            │   │
│  │  ├── 自定义功能扩展                                         │   │
│  │  └── 任意结构                                               │   │
│  │                                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 插件接口

```typescript
// plugin/types.ts

export interface PluginManifest {
  name: string;
  version: string;
  type: 'skill' | 'hook' | 'agent' | 'model' | 'custom';
  description: string;
  author?: string;
  homepage?: string;
  dependencies?: Record<string, string>;
  config?: Record<string, ConfigField>;
  entry: string;  // 入口文件
}

export interface ConfigField {
  type: 'string' | 'number' | 'boolean' | 'select';
  description: string;
  default?: any;
  required?: boolean;
  options?: string[];  // for select
}

export interface PluginContext {
  db: Database;
  state: StateManager;
  config: Record<string, any>;
  logger: Logger;
  emit: (event: string, data: any) => void;
  on: (event: string, handler: (data: any) => void) => void;
}

export interface Plugin {
  manifest: PluginManifest;
  activate(ctx: PluginContext): Promise<void>;
  deactivate(): Promise<void>;
}

// ==================== Skill Plugin ====================

export interface SkillPlugin extends Plugin {
  execute(args: string, ctx: PluginContext): Promise<string>;
}

// ==================== Hook Plugin ====================

export type HookEvent = 'SessionStart' | 'UserPromptSubmit' | 'PreToolUse' | 'PostToolUse' | 'Stop';

export interface HookPlugin extends Plugin {
  events: HookEvent[];
  handle(event: HookEvent, data: any, ctx: PluginContext): Promise<HookResult>;
}

export interface HookResult {
  continue: boolean;
  systemMessage?: string;
  modifiedData?: any;
}

// ==================== Agent Plugin ====================

export interface AgentPlugin extends Plugin {
  role: string;
  phase: string[];  // 可用阶段
  prompt: string;   // 系统提示词
  tools?: string[]; // 可用工具限制
}

// ==================== Model Plugin ====================

export interface ModelPlugin extends Plugin {
  adapter: ModelAdapter;
}
```

### 6.3 插件目录结构

```
~/.solar/plugins/
├── skills/
│   └── my-skill/
│       ├── manifest.json
│       ├── SKILL.md
│       └── index.ts
├── hooks/
│   └── my-hook/
│       ├── manifest.json
│       └── handler.ts
├── agents/
│   └── my-agent/
│       ├── manifest.json
│       └── agent.md
├── models/
│   └── my-model/
│       ├── manifest.json
│       └── adapter.ts
└── custom/
    └── my-extension/
        ├── manifest.json
        └── index.ts
```

### 6.4 示例插件 - Skill

```json
// plugins/skills/jira/manifest.json
{
  "name": "jira",
  "version": "1.0.0",
  "type": "skill",
  "description": "Jira 集成 - 创建/更新/查询 Issue",
  "author": "Solar Team",
  "config": {
    "jira_url": {
      "type": "string",
      "description": "Jira 服务器地址",
      "required": true
    },
    "jira_token": {
      "type": "string",
      "description": "Jira API Token",
      "required": true
    },
    "default_project": {
      "type": "string",
      "description": "默认项目 Key",
      "default": "PROJ"
    }
  },
  "entry": "index.ts"
}
```

```typescript
// plugins/skills/jira/index.ts

import type { SkillPlugin, PluginContext } from '@solar/plugin';

export default {
  manifest: require('./manifest.json'),

  async activate(ctx: PluginContext) {
    ctx.logger.info('Jira plugin activated');
  },

  async deactivate() {},

  async execute(args: string, ctx: PluginContext): Promise<string> {
    const [command, ...rest] = args.split(' ');

    switch (command) {
      case 'create':
        return await this.createIssue(rest.join(' '), ctx);
      case 'list':
        return await this.listIssues(ctx);
      case 'update':
        return await this.updateIssue(rest[0], rest.slice(1).join(' '), ctx);
      default:
        return 'Usage: /jira [create|list|update] ...';
    }
  },

  async createIssue(title: string, ctx: PluginContext) {
    const { jira_url, jira_token, default_project } = ctx.config;
    // 调用 Jira API
    // ...
    return `Created issue: ${default_project}-123`;
  }
} satisfies SkillPlugin;
```

### 6.5 插件加载器

```typescript
// plugin/loader.ts

export class PluginHost {
  private plugins: Map<string, Plugin> = new Map();
  private db: Database;
  private state: StateManager;

  constructor(pluginDir: string, db: Database, state: StateManager) {
    this.db = db;
    this.state = state;
  }

  // 加载插件
  async load(name: string): Promise<{ success: boolean; message: string }> {
    try {
      const pluginPath = await this.findPlugin(name);
      if (!pluginPath) {
        return { success: false, message: `Plugin not found: ${name}` };
      }

      const manifest = await Bun.file(`${pluginPath}/manifest.json`).json();
      const module = await import(`${pluginPath}/${manifest.entry}`);
      const plugin: Plugin = module.default;

      // 加载配置
      const config = await this.loadConfig(name, manifest.config);

      // 创建上下文
      const ctx = this.createContext(config);

      // 激活插件
      await plugin.activate(ctx);

      // 注册
      this.plugins.set(name, plugin);

      // 记录到数据库
      this.db.run(`
        INSERT INTO plugins (name, version, type, path, enabled, config)
        VALUES (?, ?, ?, ?, true, ?)
        ON CONFLICT(name) DO UPDATE SET
          version = excluded.version,
          enabled = true
      `, [name, manifest.version, manifest.type, pluginPath, JSON.stringify(config)]);

      return { success: true, message: `Plugin ${name} loaded` };
    } catch (e) {
      return { success: false, message: String(e) };
    }
  }

  // 卸载插件
  async unload(name: string): Promise<void> {
    const plugin = this.plugins.get(name);
    if (plugin) {
      await plugin.deactivate();
      this.plugins.delete(name);
      this.db.run(`UPDATE plugins SET enabled = false WHERE name = ?`, [name]);
    }
  }

  // 执行 Skill
  async executeSkill(name: string, args: string): Promise<string> {
    const plugin = this.plugins.get(name) as SkillPlugin;
    if (!plugin || plugin.manifest.type !== 'skill') {
      throw new Error(`Skill not found: ${name}`);
    }
    return plugin.execute(args, this.createContext(await this.loadConfig(name)));
  }

  // 触发 Hook
  async triggerHook(event: HookEvent, data: any): Promise<HookResult[]> {
    const results: HookResult[] = [];

    for (const [name, plugin] of this.plugins) {
      if (plugin.manifest.type === 'hook') {
        const hookPlugin = plugin as HookPlugin;
        if (hookPlugin.events.includes(event)) {
          const result = await hookPlugin.handle(event, data, this.createContext({}));
          results.push(result);
          if (!result.continue) break; // 阻止继续
        }
      }
    }

    return results;
  }

  private createContext(config: Record<string, any>): PluginContext {
    return {
      db: this.db,
      state: this.state,
      config,
      logger: new Logger(),
      emit: (event, data) => this.eventBus.emit(event, data),
      on: (event, handler) => this.eventBus.on(event, handler)
    };
  }
}
```

### 6.6 插件 CLI

```bash
# 安装插件
solar plugin install https://github.com/user/solar-plugin-jira

# 列出插件
solar plugin list

# 启用/禁用
solar plugin enable jira
solar plugin disable jira

# 配置
solar plugin config jira --set jira_url=https://xxx.atlassian.net

# 卸载
solar plugin uninstall jira
```

---

## 七、目录结构总览

```
~/.solar/
├── solar.db                    # SQLite 数据库
├── .env                        # 环境变量 (API Keys)
├── config.json                 # 全局配置
├── daemon.pid                  # Daemon PID
├── daemon.log                  # Daemon 日志
├── cache/                      # 缓存目录
│   └── *.msg.json             # 待处理消息
├── engine/                     # 本地处理引擎
│   ├── index.ts
│   ├── router.ts
│   ├── renderer.ts
│   ├── state.ts
│   └── templates/
├── daemon/                     # Daemon 服务
│   ├── server.ts
│   ├── scheduler.ts
│   ├── workflow.ts
│   └── dispatcher.ts
├── brain/                      # 多模型层
│   ├── router.ts
│   ├── types.ts
│   └── adapters/
│       ├── claude.ts
│       ├── openai.ts
│       ├── deepseek.ts
│       ├── gemini.ts
│       ├── glm.ts
│       └── minimax.ts
├── nerve/                      # SQLite 层
│   ├── schema.sql
│   ├── state-manager.ts
│   └── queries.ts
├── plugin/                     # 插件系统
│   ├── types.ts
│   ├── loader.ts
│   └── registry.ts
├── plugins/                    # 用户插件
│   ├── skills/
│   ├── hooks/
│   ├── agents/
│   ├── models/
│   └── custom/
└── bin/                        # 命令行工具
    ├── solar-daemon
    ├── solar-cli
    └── solar-plugin
```

---

## 八、启动流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Solar Startup Flow                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. 用户启动 Claude Code                                            │
│         │                                                           │
│         ▼                                                           │
│  2. SessionStart Hook 触发                                          │
│         │                                                           │
│         ▼                                                           │
│  3. 检查 Daemon 是否运行                                            │
│         │                                                           │
│    ┌────┴────┐                                                      │
│    ▼         ▼                                                      │
│  运行中    未运行                                                    │
│    │         │                                                      │
│    │         ▼                                                      │
│    │    启动 Daemon                                                 │
│    │         │                                                      │
│    │         ▼                                                      │
│    │    初始化 SQLite                                               │
│    │         │                                                      │
│    │         ▼                                                      │
│    │    加载插件                                                    │
│    │         │                                                      │
│    └────┬────┘                                                      │
│         │                                                           │
│         ▼                                                           │
│  4. 读取项目状态                                                    │
│         │                                                           │
│         ▼                                                           │
│  5. 恢复工作流状态                                                  │
│         │                                                           │
│         ▼                                                           │
│  6. 显示状态横幅 (本地渲染)                                         │
│         │                                                           │
│         ▼                                                           │
│  7. 等待用户输入                                                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 九、实现计划

| Phase | 任务 | 优先级 | 依赖 |
|-------|------|--------|------|
| **P0** | SQLite Schema + StateManager | P0 | - |
| **P0** | Daemon 骨架 + Socket 服务 | P0 | - |
| **P1** | 本地渲染引擎 + 模板 | P1 | P0 |
| **P1** | 消息队列 + 同步 | P1 | P0 |
| **P2** | 多模型适配器 (Claude/OpenAI) | P2 | P0 |
| **P2** | 模型路由策略 | P2 | P2.1 |
| **P3** | 插件系统框架 | P3 | P0 |
| **P3** | Skill/Hook 插件支持 | P3 | P3.1 |
| **P4** | 更多模型适配器 | P4 | P2 |
| **P4** | 插件市场/CLI | P4 | P3 |

---

## 十、验收标准

### Daemon
- [ ] 后台稳定运行，自动重启
- [ ] Unix Socket 响应 <10ms
- [ ] 消息队列正确同步到 SQLite

### SQLite
- [ ] 状态持久化可靠
- [ ] 查询性能满足需求
- [ ] 支持并发访问

### 多模型
- [ ] 至少支持 3 种模型后端
- [ ] 自动降级/回退
- [ ] 成本控制有效

### 插件系统
- [ ] 插件加载/卸载正常
- [ ] 插件隔离，不影响主系统
- [ ] 配置热更新

---

> 设计者: @Architect | 状态: 待审核
