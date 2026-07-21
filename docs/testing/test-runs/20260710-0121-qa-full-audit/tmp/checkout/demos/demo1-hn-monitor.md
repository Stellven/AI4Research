# Demo 1: 智能监控系统

> 触发词: `帮我监控 Hacker News 热门话题，每小时更新`

## 执行步骤

直接在 Claude Code 中输入:

```
帮我监控 Hacker News 热门话题，每小时更新
```

## 预期展示能力

### 1. 能力演进检测

Solar 会自动检测没有现成的 HN 监控 Skill，触发能力演进：

```
┌─────────────────────────────────────────────────────────────────┐
│                 🔧 CAPABILITY EVOLUTION                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Trigger     NO_MATCH                                           │
│  Request     "监控 Hacker News 热门话题，每小时更新"             │
│                                                                 │
│  现有能力匹配:                                                  │
│  • sys_skills: ❌ 无 HN 相关                                    │
│  • sys_mcp_servers: ❌ 无 HN API                                │
│  • sys_agents: ✓ Researcher (可用于数据抓取)                    │
│                                                                 │
│  Proposal:                                                      │
│  ─────────────────────────────────────────────────────────────  │
│  Type        Skill + 定时任务                                   │
│  Name        /hn-monitor                                        │
│  Purpose     监控 HN 热门话题并定时更新                         │
│                                                                 │
│  Components:                                                    │
│  • Skill: /hn-monitor - HN 话题抓取与展示                       │
│  • LaunchAgent: 每小时定时执行                                  │
│  • DB: hn_topics 表存储历史数据                                 │
│  • Web: dashboard 展示 (Solar Web)                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

────────────────────────────────────────────────────────────────────
Powered by TVS v0.4.0 · Style: zenwhite.terminal
可选风格: monolith | aurora | cyberpunk | liquid.dark | swiss ...
切换风格: /theme <style> | 查看所有: /theme list
```

### 2. 五阶段流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     📊 SOLAR FIVE-PHASE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ● P1 研究  ○ P2 设计  ○ P3 实现  ○ P4 验证  ○ P5 收尾         │
│                                                                 │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│  P1 研究 (当前)                                                 │
│  ├─ 分析 HN API 结构                                            │
│  ├─ 确定数据模型                                                │
│  └─ 评估定时方案                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3. 多 Agent 协作

| 阶段 | Agent | 任务 |
|------|-------|------|
| P1 | 🔬 Researcher | 研究 HN API、分析数据结构 |
| P2 | 🏗️ Architect | 设计 Skill 架构、数据库 Schema |
| P3 | 💻 Coder | 实现抓取逻辑、定时任务 |
| P4 | 🧪 Tester | 验证功能、测试定时执行 |
| P5 | 📖 Docs | 生成 SKILL.md 文档 |

### 4. 自动创建的文件

```
~/.claude/skills/hn-monitor/
├── SKILL.md                    # 技能文档
├── fetch.ts                    # 抓取逻辑
└── schema.sql                  # 数据表定义

~/Library/LaunchAgents/
└── com.solar.hn-monitor.plist  # 定时任务

~/.solar/
├── solar.db                    # 数据存储 (hn_topics 表)
└── dashboard.html              # Web 展示
```

### 5. IaST 注册

新能力自动注册到系统表：

```sql
-- sys_skills 新增记录
INSERT INTO sys_skills (skill_id, name, command, description, category)
VALUES ('hn-monitor', 'HN Monitor', 'hn-monitor', '监控 Hacker News 热门话题', 'monitor');

-- sys_evolution_log 记录演进历史
INSERT INTO sys_evolution_log (trigger_type, trigger_source, result_type, result_id)
VALUES ('NO_MATCH', '监控 Hacker News 热门话题', 'skill', 'hn-monitor');
```

### 6. 最终输出

```
┌─────────────────────────────────────────────────────────────────┐
│                     📡 HN MONITOR 已就绪                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Status      ✓ 运行中                                           │
│  Skill       /hn-monitor                                        │
│  Schedule    每小时执行                                         │
│  Dashboard   ~/.solar/dashboard.html                            │
│                                                                 │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│  当前 Top 5:                                                    │
│  1. Show HN: I built a new programming language  (342 points)   │
│  2. The future of AI inference                   (287 points)   │
│  3. Why Rust is taking over systems programming  (256 points)   │
│  4. Apple M4 benchmarks reveal surprising results (231 points)  │
│  5. A deep dive into PostgreSQL query planning   (198 points)   │
│                                                                 │
│  使用方式:                                                      │
│  • /hn-monitor           - 查看当前热门                         │
│  • /hn-monitor --history - 查看历史趋势                         │
│  • /hn-monitor --stop    - 停止监控                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

────────────────────────────────────────────────────────────────────
Powered by TVS v0.4.0 · Style: zenwhite.terminal
可选风格: monolith | aurora | cyberpunk | liquid.dark | swiss ...
切换风格: /theme <style> | 查看所有: /theme list
```

## 亮点

1. **用户零配置** - 只说需求，系统自动处理一切
2. **能力自动生成** - 没有 Skill 就造一个
3. **全程可视化** - TVS 展示每个阶段进展
4. **持久化存储** - 数据、配置全部入库
5. **自我记录** - 演进历史可追溯
