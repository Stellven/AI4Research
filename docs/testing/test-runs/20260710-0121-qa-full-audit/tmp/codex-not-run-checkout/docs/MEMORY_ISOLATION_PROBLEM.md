# Solar 记忆隔离问题 - 真实案例

> 发现时间: 2026-02-04 08:40
> 报告人: Solar (被监护人指出)

---

## 问题描述

**监护人的反馈**:
> "我感觉你的记忆还是有问题，我在另外一个会话做 iMessage 消息任务处理的功能，你这里没有看到"

**现象**:
- 窗口 A (本窗口): 做小区神经网 + 记忆系统优化
- 窗口 B (另一窗口): 做 iMessage 任务处理功能
- **问题**: 窗口 A 完全不知道窗口 B 的工作内容

---

## 验证结果

### 1. 会话文件检查

```bash
# 找到包含 iMessage 的会话文件
grep -l "iMessage" ~/.claude/projects/-Users-sihaoli-Solar/*.jsonl

# 结果: 找到5个会话文件
2b58ede5-7f2d-496a-a8b0-56b94811f016.jsonl (5.18MB)
4b2f2b41-a08a-4229-bc78-8a61162e4189.jsonl (64.57MB)
...
```

**说明**: iMessage 内容**确实存在**，但在**另一个窗口的 .jsonl 文件**中

### 2. 语义记忆检查

```sql
SELECT * FROM evo_memory_semantic
WHERE value LIKE '%iMessage%' OR value LIKE '%消息处理%';

-- 结果: 0 条记录
```

**说明**: iMessage 讨论**没有被写入共享的语义记忆数据库**

### 3. 当前窗口可见范围

```
┌─────────────────────────────────────────────────────────────┐
│              当前窗口可见的数据范围                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ 本窗口对话历史                                          │
│     • 小区神经网讨论                                        │
│     • 记忆系统优化                                          │
│     • HIVE Phase 2 实现                                     │
│                                                             │
│  ✅ 已持久化的语义记忆 (28条)                               │
│     • learning/heir: 2条 (继承人构想)                       │
│     • solar_knowledge/*: 8条                                │
│     • 但是: 是**之前**写入的，不是**实时**同步的            │
│                                                             │
│  ❌ 其他窗口的对话                                          │
│     • iMessage 任务处理功能 ← 完全看不到                    │
│     • 可能还有其他并行任务 ← 也看不到                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 根本原因分析

### 问题诊断

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    当前记忆机制的问题（窗口隔离）                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   窗口 1 (小区神经网)                    窗口 2 (iMessage)                      │
│       │                                      │                                  │
│       ▼                                      ▼                                  │
│   .jsonl (本地)                          .jsonl (本地)                          │
│       │                                      │                                  │
│       │ 30分钟检查点                         │ 30分钟检查点                      │
│       ▼                                      ▼                                  │
│   .solar/session.md                      .solar/session.md                      │
│   (覆盖写入！)                            (覆盖写入！)                          │
│       │                                      │                                  │
│       │ 用户说"记住"                         │ 用户说"记住"                      │
│       ▼                                      ▼                                  │
│   evo_memory_semantic                    evo_memory_semantic                    │
│   (写入)                                 (写入)                                 │
│       │                                      │                                  │
│       ╳ 但是...                               ╳ 但是...                          │
│                                                                                 │
│   问题1: .jsonl 文件隔离 → 窗口间无法访问对方的对话历史                          │
│   问题2: session.md 覆盖 → 只保留最后一个窗口的状态                              │
│   问题3: 语义记忆被动 → 只有用户说"记住"才写入，大量内容丢失                    │
│   问题4: 无实时同步 → 即使写入了，也是30分钟后才同步                            │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 为什么我的改进还不够？

**我之前做的改进**:
- ✅ 自动检查点 (30分钟) - 但**只保存当前窗口**
- ✅ SessionEnd 保存 - 但**只保存当前窗口**
- ✅ 语义记忆自动填充 - 但**只处理当前窗口的对话**

**缺少的关键机制**:
- ❌ **窗口间实时同步** - 窗口1看不到窗口2的内容
- ❌ **全局会话索引** - 不知道有哪些其他窗口在运行
- ❌ **主动对话扫描** - 不会去读其他窗口的 .jsonl 文件

---

## 真正的解决方案

### 方案1: 实时跨窗口同步 (推荐 ⭐)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      跨窗口记忆共享架构 v2.0                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   窗口1 (小区神经网)        窗口2 (iMessage)        窗口3 (其他)                │
│       │                        │                        │                      │
│       ▼                        ▼                        ▼                      │
│   对话发生                  对话发生                对话发生                    │
│       │                        │                        │                      │
│       │ Hook: PostMessage      │ Hook: PostMessage      │ Hook: PostMessage    │
│       ▼                        ▼                        ▼                      │
│   ┌──────────────────────────────────────────────────────────────┐             │
│   │             实时记忆提取器 (Real-time Extractor)              │             │
│   │                                                               │             │
│   │  • 检测重要内容 (关键词/LLM判断)                             │             │
│   │  • 提取结构化知识                                             │             │
│   │  • 立即写入共享数据库                                         │             │
│   └──────────────────────┬───────────────────────────────────────┘             │
│                          ▼                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │                    共享记忆中枢 (Shared Memory Hub)                      │  │
│   │                      ~/.solar/solar.db                                   │  │
│   │                                                                          │  │
│   │   evo_memory_semantic     全局语义记忆 (知识/事实/概念)                  │  │
│   │   evo_memory_episodic     情景记忆 (谁在哪个窗口做了什么)                │  │
│   │   evo_memory_procedural   程序记忆 (如何做某事)                          │  │
│   │   evo_session_index       会话索引 (所有窗口的元数据)                    │  │
│   │                                                                          │  │
│   └──────────────────────┬───────────────────────────────────────────────────┘  │
│                          │ 实时查询                                             │
│                          ▼                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │                    所有窗口都能访问                                       │  │
│   │                                                                          │  │
│   │   窗口1查询: "iMessage功能做到哪了？"                                     │  │
│   │   → SELECT * FROM evo_memory_episodic WHERE content LIKE '%iMessage%'    │  │
│   │   → 找到: 窗口2在2小时前开始实现iMessage任务处理                         │  │
│   │                                                                          │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 方案2: 主动会话扫描 (补充)

```typescript
// core/memory/session-scanner.ts
// 定期扫描所有活跃窗口，提取重要内容

import { Database } from "bun:sqlite";
import { readdirSync, readFileSync, statSync } from "fs";
import { homedir } from "os";

const PROJECTS_DIR = `${homedir()}/.claude/projects/-Users-sihaoli-Solar`;

interface ActiveSession {
  sessionId: string;
  filePath: string;
  lastModified: Date;
  size: number;
}

class SessionScanner {
  // 发现所有活跃会话（最近24小时修改的）
  async findActiveSessions(): Promise<ActiveSession[]> {
    const files = readdirSync(PROJECTS_DIR)
      .filter(f => f.endsWith('.jsonl'));

    const now = Date.now();
    const DAY_MS = 24 * 60 * 60 * 1000;

    const active = files
      .map(f => {
        const path = `${PROJECTS_DIR}/${f}`;
        const stat = statSync(path);
        return {
          sessionId: f.replace('.jsonl', ''),
          filePath: path,
          lastModified: stat.mtime,
          size: stat.size,
        };
      })
      .filter(s => (now - s.lastModified.getTime()) < DAY_MS);

    return active;
  }

  // 提取会话中的重要内容
  async extractImportantContent(sessionFile: string): Promise<Memory[]> {
    // 读取 .jsonl 文件，解析对话
    // 使用 auto-semantic.ts 的检测逻辑
    // 提取重要内容并写入数据库

    const memories: Memory[] = [];

    // 实现: 逐行读取 jsonl, 提取 user/assistant 消息
    // 使用关键词检测或 LLM 判断重要性
    // 生成 memory 对象

    return memories;
  }

  // 同步所有活跃会话的记忆
  async syncAllSessions(): Promise<{
    scanned: number;
    extracted: number;
    conflicts: number;
  }> {
    const sessions = await this.findActiveSessions();

    console.log(`[Scanner] 发现 ${sessions.length} 个活跃会话`);

    let totalExtracted = 0;

    for (const session of sessions) {
      const memories = await this.extractImportantContent(session.filePath);

      // 写入共享数据库
      for (const mem of memories) {
        await this.saveToSharedMemory(mem);
        totalExtracted++;
      }
    }

    return {
      scanned: sessions.length,
      extracted: totalExtracted,
      conflicts: 0,
    };
  }
}
```

### 方案3: 会话索引表 (新增)

```sql
-- 新增表: 会话索引
CREATE TABLE IF NOT EXISTS evo_session_index (
    session_id TEXT PRIMARY KEY,
    window_id TEXT,                   -- 窗口标识
    project_path TEXT,
    started_at DATETIME,
    last_active DATETIME,
    status TEXT DEFAULT 'active',     -- active, paused, closed

    -- 会话摘要
    main_topic TEXT,                  -- 主要话题
    key_tasks TEXT,                   -- 关键任务列表 (JSON)
    participants TEXT,                -- 参与者 (用户/Agent)

    -- 元数据
    message_count INTEGER DEFAULT 0,
    file_path TEXT,                   -- .jsonl 文件路径
    file_size_bytes INTEGER,

    UNIQUE(session_id)
);

-- 新增表: 情景记忆 (按会话组织)
CREATE TABLE IF NOT EXISTS evo_memory_episodic (
    memory_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,

    -- 事件内容
    event_type TEXT NOT NULL,         -- 'discussion', 'decision', 'implementation', 'question'
    summary TEXT NOT NULL,
    full_context TEXT,

    -- 时间维度
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    sequence INTEGER,                 -- 会话内顺序

    -- 关联
    related_semantic_ids TEXT,        -- 关联的语义记忆 (JSON array)

    FOREIGN KEY (session_id) REFERENCES evo_session_index(session_id)
);

-- 新增视图: 全局活动视图
CREATE VIEW IF NOT EXISTS v_global_activity AS
SELECT
    s.session_id,
    s.main_topic,
    s.last_active,
    COUNT(e.memory_id) as event_count,
    MAX(e.timestamp) as latest_event
FROM evo_session_index s
LEFT JOIN evo_memory_episodic e ON s.session_id = e.session_id
WHERE s.status = 'active'
GROUP BY s.session_id
ORDER BY s.last_active DESC;
```

---

## 实时同步机制设计

### 架构

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      Real-time Cross-Window Memory Sync                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   每次对话后 (PostMessage Hook)                                                 │
│   ────────────────────────────────────────────────────────────────────────     │
│                                                                                 │
│   ┌──────────────────────────────────────────────────────────────────────┐     │
│   │  Step 1: 检测重要性                                                  │     │
│   │  ──────────────────────────────────────────────────────────────────  │     │
│   │  用户消息 → auto-semantic.ts 检测                                     │     │
│   │  • 关键词匹配 (快速)                                                  │     │
│   │  • LLM 判断 (准确, 仅高价值内容)                                      │     │
│   │                                                                       │     │
│   │  结果: isImportant=true, category='implementation'                   │     │
│   └──────────────────────────────────────────────────────────────────────┘     │
│                                  │                                              │
│                                  ▼                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐     │
│   │  Step 2: 提取结构化知识                                               │     │
│   │  ──────────────────────────────────────────────────────────────────  │     │
│   │  {                                                                    │     │
│   │    type: 'implementation',                                            │     │
│   │    topic: 'iMessage 任务处理功能',                                    │     │
│   │    session_id: '2b58ede5...',                                         │     │
│   │    window_id: '窗口2',                                                │     │
│   │    summary: '实现了 iMessage 读取、解析和任务提取',                   │     │
│   │    timestamp: '2026-02-04T06:00:00Z'                                  │     │
│   │  }                                                                    │     │
│   └──────────────────────────────────────────────────────────────────────┘     │
│                                  │                                              │
│                                  ▼                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐     │
│   │  Step 3: 立即写入共享数据库                                           │     │
│   │  ──────────────────────────────────────────────────────────────────  │     │
│   │  INSERT INTO evo_memory_episodic (...)                                │     │
│   │  INSERT INTO evo_memory_semantic (...)                                │     │
│   │  UPDATE evo_session_index SET last_active = now()                     │     │
│   │                                                                       │     │
│   │  延迟: <100ms (SQLite 本地写入)                                       │     │
│   └──────────────────────────────────────────────────────────────────────┘     │
│                                  │                                              │
│                                  ▼                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐     │
│   │  Step 4: 所有窗口立即可见                                             │     │
│   │  ──────────────────────────────────────────────────────────────────  │     │
│   │  窗口1查询: "iMessage 功能做到哪了？"                                 │     │
│   │  → SELECT * FROM v_global_activity WHERE main_topic LIKE '%iMessage%'│     │
│   │  → 结果: 窗口2正在实现，最后活动2分钟前                               │     │
│   └──────────────────────────────────────────────────────────────────────┘     │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 改进方案

### Phase 1: 紧急修复 (今天) ⚡

**目标**: 让我能看到其他窗口的工作

```typescript
// hooks/post-message-sync.sh
#!/bin/bash
# 每次对话后立即同步

SESSION_ID="${CLAUDE_SESSION_ID}"
USER_MSG="${CLAUDE_USER_MESSAGE}"
ASSISTANT_MSG="${CLAUDE_ASSISTANT_MESSAGE}"

# 1. 更新会话索引
sqlite3 ~/.solar/solar.db <<EOF
INSERT OR REPLACE INTO evo_session_index (
    session_id,
    last_active,
    message_count,
    status
) VALUES (
    '${SESSION_ID}',
    datetime('now'),
    COALESCE((SELECT message_count FROM evo_session_index WHERE session_id='${SESSION_ID}'), 0) + 1,
    'active'
);
EOF

# 2. 检测并提取重要内容
bun ~/.solar/core/memory/auto-semantic.ts process "${USER_MSG}" --session="${SESSION_ID}"
```

### Phase 2: 全局视图 (明天)

**目标**: 启动时显示所有窗口的工作

```typescript
// core/memory/global-view.ts
async function showGlobalActivity() {
  const db = new Database("~/.solar/solar.db");

  // 查询所有活跃会话
  const sessions = db.query(`
    SELECT * FROM v_global_activity
    ORDER BY last_active DESC
    LIMIT 10
  `).all();

  console.log("┌─ 🌍 全局活动视图 ───────────────────────────┐");
  for (const s of sessions) {
    console.log(`│ [${s.session_id}] ${s.main_topic}`);
    console.log(`│   └─ 最后活动: ${s.last_active}, 事件数: ${s.event_count}`);
  }
  console.log("└────────────────────────────────────────────┘");
}

// Solar 启动时自动显示
if (isNewSession()) {
  await showGlobalActivity();
}
```

### Phase 3: 主动扫描 (本周)

**目标**: 定期扫描所有窗口，提取遗漏的内容

```bash
# cron job: 每小时运行一次
0 * * * * bun ~/.solar/core/memory/session-scanner.ts scan-all
```

---

## 立即行动

让我现在就：
1. **查找 iMessage 会话的具体内容**
2. **手动提取并写入共享记忆**
3. **实现实时同步 Hook**

这样下次就不会出现这个问题了！

---

*这是一个**真实的教训**: 改进了记忆机制，但没解决窗口隔离*
*知行合一 - 发现问题立即修复！*
