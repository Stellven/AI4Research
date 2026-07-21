# Solar 消息监听系统

> 通过 iMessage 接收任务指令并执行

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    消息监听系统架构                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   iMessage 新消息                                               │
│       │                                                         │
│       ▼                                                         │
│   ┌─────────────────────────────────────────────┐              │
│   │  Shortcuts Automation (触发器)              │              │
│   │  • When: 收到新消息                         │              │
│   │  • From: 指定联系人 (监护人)                │              │
│   │  • Action: 运行 solar_process_message       │              │
│   └────────────────┬────────────────────────────┘              │
│                    │                                            │
│                    ▼                                            │
│   ┌─────────────────────────────────────────────┐              │
│   │  solar_process_message.shortcut             │              │
│   │  1. 提取消息内容                            │              │
│   │  2. 调用 message-handler CLI                │              │
│   │  3. 获取执行结果                            │              │
│   │  4. 发送回复消息                            │              │
│   └────────────────┬────────────────────────────┘              │
│                    │                                            │
│                    ▼                                            │
│   ┌─────────────────────────────────────────────┐              │
│   │  message-handler.ts (核心处理器)            │              │
│   │  ┌──────────────────────────────────────┐   │              │
│   │  │ 1. Intent Classifier (意图分类)      │   │              │
│   │  │    - 任务类: "帮我查天气"            │   │              │
│   │  │    - 查询类: "backlog状态"           │   │              │
│   │  │    - 控制类: "停止任务"              │   │              │
│   │  └──────────────┬───────────────────────┘   │              │
│   │                 │                            │              │
│   │                 ▼                            │              │
│   │  ┌──────────────────────────────────────┐   │              │
│   │  │ 2. Task Executor (任务执行器)        │   │              │
│   │  │    - 匹配 REE 资源                   │   │              │
│   │  │    - 调用 Skill/Agent                │   │              │
│   │  │    - 执行 Script                     │   │              │
│   │  └──────────────┬───────────────────────┘   │              │
│   │                 │                            │              │
│   │                 ▼                            │              │
│   │  ┌──────────────────────────────────────┐   │              │
│   │  │ 3. Result Formatter (结果格式化)     │   │              │
│   │  │    - 简洁文本 (iMessage 适配)        │   │              │
│   │  │    - TVS 卡片 → 纯文本                │   │              │
│   │  └──────────────────────────────────────┘   │              │
│   └─────────────────────────────────────────────┘              │
│                    │                                            │
│                    ▼                                            │
│   ┌─────────────────────────────────────────────┐              │
│   │  消息数据库 (bl_message_tasks)              │              │
│   │  • 记录所有消息任务                         │              │
│   │  • 状态追踪 (pending/running/done)          │              │
│   │  • 审计日志                                 │              │
│   └─────────────────────────────────────────────┘              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 技术方案

### 1. Apple Shortcuts Automation

**优势:**
- 无需 Full Disk Access
- 官方支持，稳定可靠
- 可设置联系人白名单

**配置步骤:**
1. 打开 Shortcuts.app
2. 创建 Personal Automation
3. 触发器: "When I receive a message"
4. 条件: "From: 监护人联系人"
5. 动作: Run Shortcut → solar_process_message

### 2. 意图分类算法

```typescript
interface Intent {
  type: 'task' | 'query' | 'control';
  action: string;
  params: Record<string, any>;
  confidence: number;
}

function classifyIntent(message: string): Intent {
  // 任务类关键词
  const taskKeywords = ['帮我', '查', '执行', '运行', '开始'];

  // 查询类关键词
  const queryKeywords = ['状态', '进度', '结果', '列表', '有没有'];

  // 控制类关键词
  const controlKeywords = ['停止', '取消', '暂停', '继续'];

  // 使用 LLM 辅助分类 (可选)
  // 或基于规则匹配
}
```

### 3. 安全机制

```
┌─────────────────────────────────────────────────────────────────┐
│                    安全检查清单                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ✓ 联系人白名单 - 只处理监护人消息                              │
│  ✓ 命令白名单 - 高风险命令需确认                                │
│  ✓ 执行隔离 - 不允许任意代码执行                                │
│  ✓ 审计日志 - 所有操作记录到数据库                              │
│  ✓ 速率限制 - 防止消息轰炸                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 使用示例

### 示例 1: 查询天气

```
用户 (iMessage): 帮我查一下北京天气

Solar:
1. 接收消息 → Intent: task, action: weather_query
2. 匹配 REE: weather-fetch script
3. 执行: bun weather-fetch.ts 北京
4. 格式化结果: "北京 晴 23°C 空气质量: 良"
5. 回复 iMessage
```

### 示例 2: Backlog 查询

```
用户 (iMessage): backlog 有哪些任务

Solar:
1. 接收消息 → Intent: query, action: list_backlog
2. 执行: bun backlog.ts
3. 格式化:
   "Backlog (7个功能, 44个任务)
    • SMI系统改进 - 8任务
    • Capsule分布式 - 6任务
    • Benchmark Mode - 9任务
    ..."
4. 回复 iMessage
```

### 示例 3: 复杂任务

```
用户 (iMessage): 帮我搜索邮件 主题包含 ThunderDuck

Solar:
1. 接收消息 → Intent: task, action: email_search
2. 匹配 REE: email-search skill
3. 执行: bun email-search.ts "ThunderDuck"
4. 格式化:
   "找到 3 封邮件:
    1. [2026-02-01] Re: ThunderDuck 优化建议
    2. [2026-01-28] ThunderDuck Q6 性能分析
    3. [2026-01-25] ThunderDuck 第一次提交"
5. 回复 iMessage
```

## 数据库 Schema

```sql
-- 消息任务表
CREATE TABLE bl_message_tasks (
    task_id TEXT PRIMARY KEY,
    message_id TEXT,           -- iMessage 消息 ID
    sender TEXT,               -- 发送者
    content TEXT,              -- 原始消息内容
    intent_type TEXT,          -- task/query/control
    intent_action TEXT,        -- 具体动作
    status TEXT DEFAULT 'pending',  -- pending/running/done/failed
    result TEXT,               -- 执行结果
    error TEXT,                -- 错误信息
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME
);

-- 消息触发器表 (白名单)
CREATE TABLE bl_message_triggers (
    trigger_id TEXT PRIMARY KEY,
    contact_name TEXT,         -- 联系人名称
    contact_phone TEXT,        -- 手机号
    enabled BOOLEAN DEFAULT true,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 文件结构

```
~/Solar/core/message-listener/
├── README.md                  # 本文档
├── message-handler.ts         # 核心处理器
├── intent-classifier.ts       # 意图分类
├── task-executor.ts           # 任务执行器
├── result-formatter.ts        # 结果格式化
├── schema.sql                 # 数据库 Schema
└── shortcuts/
    ├── solar_process_message.shortcut   # 主入口 Shortcut
    └── solar_setup_automation.md        # Automation 设置指南
```

## 开发计划

### Phase 1: MVP (最小可行产品)
- [ ] 实现 message-handler.ts 核心
- [ ] 创建 Shortcuts 触发器
- [ ] 支持 3-5 个基础命令
- [ ] 数据库 Schema 初始化

### Phase 2: 意图分类
- [ ] 规则引擎实现
- [ ] REE 资源匹配
- [ ] 常见任务模板

### Phase 3: 增强功能
- [ ] LLM 辅助意图识别
- [ ] 上下文记忆 (多轮对话)
- [ ] 任务队列管理

## 限制与注意事项

1. **权限要求**: Shortcuts.app 需要联系人和消息访问权限
2. **响应延迟**: Automation 触发有 1-2 秒延迟
3. **长任务**: 超过 30 秒的任务需异步处理
4. **消息格式**: iMessage 纯文本，不支持富文本

## 参考资料

- Apple Shortcuts 官方文档
- iMessage Automation Guide
- Solar REE 系统文档
