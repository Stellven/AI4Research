# Solar Reply System - 智能回复系统设计

> 基于业界最佳实践的多通道智能回复系统

## 架构概览

```
┌─ 消息输入 ──────────────────────────────────────────────────┐
│  iMessage / Gmail / Telegram / Webhook                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─ 任务处理 ──────────────────────────────────────────────────┐
│  MessageIngester → 任务队列 → Executor → 结果               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─ 智能回复系统 ──────────────────────────────────────────────┐
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  意图分析    │→ │  类型选择    │→ │  格式适配    │      │
│  │  (用户要什么) │  │  (回复类型)  │  │  (通道适配)  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                              ↓                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                    回复生成器                         │  │
│  │  Template Engine + LLM Refinement + Channel Adapter   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─ 原通道回复 ────────────────────────────────────────────────┐
│  iMessage(AppleScript) / Gmail(himalaya) / Telegram(Bot)   │
└─────────────────────────────────────────────────────────────┘
```

## 回复类型分类 (基于业界最佳实践)

### 1. 简短回复类 (Brief)

| 类型 | 用途 | 长度 | 示例场景 |
|------|------|------|----------|
| `ack` | 确认收到 | 1句 | "收到，处理中" |
| `quick_answer` | 快速回答 | 1-3句 | 天气、时间、简单问题 |
| `status` | 状态更新 | 2-5句 | 任务进度 |
| `notification` | 通知提醒 | 1-2句 | 完成通知 |

### 2. 摘要类 (Summary)

| 类型 | 用途 | 长度 | 示例场景 |
|------|------|------|----------|
| `tldr` | 一句话总结 | 1句 | 文章核心观点 |
| `bullet_summary` | 要点摘要 | 3-7条 | 会议纪要、文章要点 |
| `executive_summary` | 管理层摘要 | 1段 | 报告摘要 |
| `digest` | 内容精选 | 多条 | 每日新闻精选 |

### 3. 分析类 (Analysis)

| 类型 | 用途 | 长度 | 示例场景 |
|------|------|------|----------|
| `insight` | 洞察分析 | 中等 | 数据分析结论 |
| `comparison` | 对比分析 | 表格+文字 | 方案对比 |
| `pros_cons` | 利弊分析 | 列表 | 决策参考 |
| `trend` | 趋势分析 | 图表+文字 | 市场趋势 |

### 4. 报告类 (Report)

| 类型 | 用途 | 长度 | 示例场景 |
|------|------|------|----------|
| `research_report` | 研究报告 | 长文 | 技术调研 |
| `tech_spec` | 技术方案 | 结构化 | 架构设计 |
| `review` | 评审报告 | 中等 | 代码/文档评审 |
| `progress_report` | 进度报告 | 中等 | 项目周报 |

### 5. 行动类 (Action)

| 类型 | 用途 | 长度 | 示例场景 |
|------|------|------|----------|
| `todo_list` | 待办清单 | 列表 | 任务分解 |
| `action_items` | 行动项 | 列表 | 会议跟进 |
| `recommendation` | 推荐建议 | 列表+理由 | 选型建议 |
| `next_steps` | 下一步 | 列表 | 工作安排 |

## 意图分析规则

```typescript
interface ReplyIntent {
  expectation: 'quick' | 'detailed' | 'actionable' | 'informative';
  format: 'text' | 'list' | 'table' | 'report';
  urgency: 'immediate' | 'normal' | 'low';
  depth: 'surface' | 'moderate' | 'deep';
}

const INTENT_PATTERNS = [
  // 快速回复
  { pattern: /^(是|否|好|不|对|错)/i, type: 'quick_answer' },
  { pattern: /天气|时间|日期|几点/i, type: 'quick_answer' },

  // 摘要
  { pattern: /总结|概括|摘要|要点|精华/i, type: 'bullet_summary' },
  { pattern: /一句话|简单说|简短/i, type: 'tldr' },

  // 分析
  { pattern: /分析|研究|看看|了解|深入/i, type: 'insight' },
  { pattern: /对比|比较|哪个好|选择/i, type: 'comparison' },
  { pattern: /优缺点|利弊|好处坏处/i, type: 'pros_cons' },

  // 报告
  { pattern: /报告|方案|设计|规划/i, type: 'research_report' },
  { pattern: /技术方案|架构|实现/i, type: 'tech_spec' },
  { pattern: /评审|review|检查/i, type: 'review' },

  // 行动
  { pattern: /该做什么|下一步|行动|计划/i, type: 'action_items' },
  { pattern: /推荐|建议|选哪个/i, type: 'recommendation' },
  { pattern: /清单|列表|todo/i, type: 'todo_list' },
];
```

## 通道适配规则

### iMessage (短消息优先)

```typescript
const IMESSAGE_LIMITS = {
  maxLength: 2000,        // 字符限制
  preferredLength: 500,   // 推荐长度
  supportImages: true,    // 支持图片
  supportLinks: true,     // 支持链接
  formatting: 'plain',    // 纯文本
};

// 长内容处理策略
const IMESSAGE_LONG_CONTENT = {
  strategy: 'split_with_summary',  // 先发摘要，再分段发
  summaryFirst: true,              // 摘要优先
  maxMessages: 5,                  // 最多拆分条数
};
```

### Gmail (富文本支持)

```typescript
const GMAIL_LIMITS = {
  maxLength: 100000,       // 邮件无严格限制
  preferredLength: 5000,   // 推荐长度
  supportImages: true,     // 支持内嵌图片
  supportLinks: true,      // 支持链接
  supportHtml: true,       // 支持 HTML
  formatting: 'html',      // HTML 格式
};

// 回复格式
const GMAIL_FORMAT = {
  includeQuote: true,      // 引用原文
  signatureEnabled: true,  // 添加签名
  subjectPrefix: 'Re: ',   // 主题前缀
};
```

### Telegram (Markdown 支持)

```typescript
const TELEGRAM_LIMITS = {
  maxLength: 4096,         // 消息限制
  preferredLength: 1000,   // 推荐长度
  supportImages: true,     // 支持图片
  supportLinks: true,      // 支持链接
  formatting: 'markdown',  // Markdown
};
```

## 回复模板

### 快速回答模板

```typescript
const TEMPLATES = {
  quick_answer: {
    weather: '{{city}}: {{condition}} {{temp}} 风速{{wind}} 湿度{{humidity}}',
    time: '现在是 {{time}}',
    ack: '收到，{{action}}',
  },

  bullet_summary: `
**摘要**

{{#each points}}
• {{this}}
{{/each}}

{{#if source}}
---
来源: {{source}}
{{/if}}
`,

  insight: `
**{{title}}**

{{summary}}

**关键发现:**
{{#each findings}}
{{@index}}. {{this}}
{{/each}}

**结论:** {{conclusion}}
`,

  comparison: `
**{{title}}**

| 维度 | {{optionA}} | {{optionB}} |
|------|-------------|-------------|
{{#each dimensions}}
| {{name}} | {{a}} | {{b}} |
{{/each}}

**建议:** {{recommendation}}
`,

  tech_spec: `
# {{title}}

## 背景
{{background}}

## 目标
{{#each goals}}
- {{this}}
{{/each}}

## 技术方案
{{solution}}

## 实现步骤
{{#each steps}}
### {{@index}}. {{title}}
{{description}}
{{/each}}

## 风险与缓解
{{#each risks}}
- **{{name}}**: {{mitigation}}
{{/each}}
`,
};
```

## 数据库 Schema

```sql
-- 回复类型配置表
CREATE TABLE IF NOT EXISTS bl_reply_types (
    type_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,           -- brief, summary, analysis, report, action
    name TEXT NOT NULL,
    description TEXT,
    template TEXT,                    -- Handlebars 模板
    channel_overrides TEXT,           -- JSON: 通道特定配置
    priority INTEGER DEFAULT 50,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 回复历史表
CREATE TABLE IF NOT EXISTS bl_reply_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES bl_message_tasks(id),
    reply_type TEXT REFERENCES bl_reply_types(type_id),
    channel TEXT NOT NULL,            -- imessage, gmail, telegram
    content TEXT NOT NULL,
    status TEXT DEFAULT 'pending',    -- pending, sent, failed
    sent_at DATETIME,
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 通道配置表
CREATE TABLE IF NOT EXISTS bl_reply_channels (
    channel_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    max_length INTEGER,
    formatting TEXT,                  -- plain, markdown, html
    config TEXT,                      -- JSON: 通道特定配置
    enabled INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 意图-回复类型映射视图
CREATE VIEW IF NOT EXISTS v_intent_reply_mapping AS
SELECT
    mt.parsed_intent,
    rt.type_id as reply_type,
    rt.category,
    rt.template,
    COUNT(*) as usage_count,
    AVG(CASE WHEN rh.status = 'sent' THEN 1 ELSE 0 END) as success_rate
FROM bl_message_tasks mt
LEFT JOIN bl_reply_history rh ON mt.id = rh.task_id
LEFT JOIN bl_reply_types rt ON rh.reply_type = rt.type_id
GROUP BY mt.parsed_intent, rt.type_id;
```

## 实现文件

| 文件 | 用途 |
|------|------|
| `~/Solar/core/reply/reply-analyzer.ts` | 意图分析，选择回复类型 |
| `~/Solar/core/reply/reply-generator.ts` | 生成回复内容 |
| `~/Solar/core/reply/channel-adapter.ts` | 通道适配器 |
| `~/Solar/core/reply/reply-sender.ts` | 发送回复 |
| `~/Solar/core/reply/templates/` | 回复模板 |
| `~/Solar/core/reply/schema.sql` | 数据库 Schema |

## 参考来源

- [Agentic LLM Best Practices 2025](https://datasciencedojo.com/blog/agentic-llm-in-2025/)
- [LLM Structured Outputs](https://news.ycombinator.com/item?id=46635309)
- [CO-STAR Framework](https://guides.library.cmu.edu/LLM_best_practices/)
- [Knock MCP Server](https://github.com/modelcontextprotocol/servers) - 多通道消息
- [agentmail-toolkit](https://github.com/modelcontextprotocol/servers) - AI Agent 邮件
- [claude-code-notifier](https://github.com/hta218/claude-code-notifier) - 通知系统
