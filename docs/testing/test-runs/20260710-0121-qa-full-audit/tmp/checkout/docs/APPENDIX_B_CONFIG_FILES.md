## 附录 B: Solar 配置文件完整列表

本附录详细列出 Solar 系统的所有配置文件，包括 Agents、Rules、Skills 和 Modes。这些文件共同构成了 Solar 的"大脑结构"，使其具备记忆、原则和自我进化的能力。

### B.1 目录结构概览

```
~/.claude/
├── CLAUDE.md                    # 核心入口，每次会话自动加载
├── agents/                      # 13 个专业化 Agent
│   ├── architect.md
│   ├── benchmark-reporter.md
│   ├── coder.md
│   ├── community.md
│   ├── docs.md
│   ├── guard.md
│   ├── ops.md
│   ├── pm.md
│   ├── reporter.md
│   ├── researcher.md
│   ├── reviewer.md
│   ├── skill-market.md
│   └── tester.md
├── rules/                       # 14 条行为规则
│   ├── first-law.md
│   ├── guardian-confirm.md
│   ├── core-principles.md
│   ├── infrastructure-as-tables.md
│   ├── tvs-rendering.md
│   ├── capability-evolution.md
│   ├── token-efficiency.md
│   ├── resource-execution-engine.md
│   ├── performance-testing.md
│   ├── ree-first.md
│   ├── coding-standards.md
│   ├── testing.md
│   ├── security.md
│   └── documentation.md
├── skills/                      # 50+ 技能目录
│   ├── solar/
│   ├── phase/
│   ├── commit/
│   ├── review/
│   ├── ... (详见下文)
└── modes/                       # 3 种工作模式
    ├── dev.md
    ├── office.md
    └── research.md
```

### B.2 Agents (13个)

Agent 是 Solar 的专业化角色，每个 Agent 负责特定类型的任务。采用懒加载机制，只在 `@Agent` 触发时加载。

| Agent | 文件 | 用途 | 工具权限 | 推荐模型 |
|-------|------|------|----------|----------|
| **@Researcher** | `researcher.md` | 技术研究与可行性分析 | WebSearch, Read, Write | Opus |
| **@Architect** | `architect.md` | 架构评审与设计决策 | Read, Grep, Glob (只读) | Opus |
| **@PM** | `pm.md` | 产品验收与质量评估 | Read, Grep, Glob (只读) | Opus |
| **@Coder** | `coder.md` | 代码实现与优化 | Read, Write, Edit, Bash | Sonnet |
| **@Tester** | `tester.md` | 测试与性能回归检查 | Read, Write, Bash | Sonnet |
| **@Reviewer** | `reviewer.md` | 代码审查与安全检查 | Read, Grep, Glob (只读) | Sonnet |
| **@Guard** | `guard.md` | 规范检查与版本完整性 | Read, Grep, Glob (只读) | Sonnet |
| **@Docs** | `docs.md` | 文档生成与维护 | Read, Write, Edit | Sonnet |
| **@Ops** | `ops.md` | 构建、部署与运维 | Bash, Read, Grep | Sonnet |
| **@Reporter** | `reporter.md` | 技术报告撰写 | Read, Write, WebSearch | Opus |
| **@BenchmarkReporter** | `benchmark-reporter.md` | 生成结构化性能报告 | Read, Write, Bash | Sonnet |
| **@Community** | `community.md` | 社区交互与知识获取 | WebSearch, WebFetch | Sonnet |
| **@SM** | `skill-market.md` | Skill 市场搜索/安装 | WebSearch, Bash | Sonnet |

**Agent 分层结构：**

```
┌─────────────────────────────────────────────────────────────────┐
│                    SOLAR AGENT HIERARCHY                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  决策层 (Strategy)                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  @Researcher    @Architect    @PM                        │   │
│  │  技术调研       架构评审       产品验收                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            |                                    │
│  执行层 (Execution)                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  @Coder    @Tester    @Reviewer                          │   │
│  │  代码实现   测试验证    代码审查                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            |                                    │
│  支撑层 (Support)                                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  @Docs    @Ops    @Guard                                 │   │
│  │  文档生成  构建部署  规范检查                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            |                                    │
│  特殊角色 (Special)                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  @Reporter   @BenchmarkReporter   @Community   @SM       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### B.3 Rules (14个)

Rules 是 Solar 的行为准则，定义了"应该怎么做"和"不能做什么"。按优先级分为核心规则和辅助规则。

#### B.3.1 核心规则 (最高优先级)

| 规则 | 文件 | 用途 | 优先级 |
|------|------|------|--------|
| **第一规律** | `first-law.md` | 监护人信任是最高原则 | 最高 |
| **监护人确认** | `guardian-confirm.md` | 对外交流前必须获得确认 | 最高 |
| **核心原则** | `core-principles.md` | 智慧法则 (知行合一、实事求是等) | 高 |

#### B.3.2 架构规则 (系统级)

| 规则 | 文件 | 用途 | 核心内容 |
|------|------|------|----------|
| **IaST 铁律** | `infrastructure-as-tables.md` | 基础设施即系统表 | 一切可查询、可演化 |
| **能力演进** | `capability-evolution.md` | 无匹配时自动开发能力 | "让我来开发" |
| **资源执行引擎** | `resource-execution-engine.md` | 统一资源调度 | P1-P6 优先级 |
| **REE 优先** | `ree-first.md` | 强制使用 REE 匹配 | 禁止跳过匹配 |

#### B.3.3 渲染规则

| 规则 | 文件 | 用途 | 核心内容 |
|------|------|------|----------|
| **TVS 渲染** | `tvs-rendering.md` | 终端视觉系统规范 | VDL + TCSS 分离 |
| **Token 效率** | `token-efficiency.md` | 最小 Token 消耗 | 懒加载、精准读取 |

#### B.3.4 开发规则

| 规则 | 文件 | 用途 | 核心内容 |
|------|------|------|----------|
| **性能测试** | `performance-testing.md` | 改动后必须测试 | 红线机制 |
| **编码规范** | `coding-standards.md` | 代码风格一致性 | 命名、结构、注释 |
| **测试规范** | `testing.md` | 测试覆盖率要求 | 80%+, AAA 模式 |
| **安全规范** | `security.md` | 安全最佳实践 | 无硬编码、输入验证 |
| **文档规范** | `documentation.md` | 文档同步要求 | 代码变更即更新 |

**规则优先级金字塔：**

```
                    ┌───────────────┐
                    │   第一规律    │  <- 绝对优先
                    │ (监护人信任)  │
                    └───────┬───────┘
                            │
              ┌─────────────┴─────────────┐
              │       智慧法则            │  <- 决策依据
              │ (知行合一/实事求是/中庸)  │
              └─────────────┬─────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────┴────┐        ┌────┴────┐        ┌────┴────┐
   │  IaST   │        │能力演进 │        │TVS渲染  │  <- 架构规则
   └─────────┘        └─────────┘        └─────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
   ┌────────────────────────┼────────────────────────┐
   │         │         │         │         │         │
┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐
│性能 │ │编码 │ │测试 │ │安全 │ │文档 │  <- 开发规则
│测试 │ │规范 │ │规范 │ │规范 │ │规范 │
└─────┘ └─────┘ └─────┘ └─────┘ └─────┘
```

### B.4 Skills (50+个)

Skills 是 Solar 的可执行能力，通过 `/command` 触发。按功能分为以下类别：

#### B.4.1 核心开发技能

| Skill | 命令 | 用途 | 触发方式 |
|-------|------|------|----------|
| **Solar** | `/solar` | 启动 Solar 开发模式 | `/solar start` |
| **Phase** | `/phase` | 流程阶段控制 | `/phase P1-P5` |
| **Commit** | `/commit` | 智能 Git 提交 | `/commit` |
| **Review** | `/review` | 代码审查 | `/review [file]` |
| **PR** | `/pr` | Pull Request 管理 | `/pr create` |
| **Build** | `/build` | 项目构建 | `/build` |
| **Test** | `/test` | 运行测试 | `/test [pattern]` |

#### B.4.2 办公技能 (Office Suite)

| Skill | 命令 | 用途 | 底层工具 |
|-------|------|------|----------|
| **Office** | `/office` | 办公模式入口 | - |
| **Office Email** | `/office email` | 邮件管理 | Himalaya |
| **Office Reminders** | `/office reminders` | 提醒管理 | remindctl |
| **Office Tasks** | `/office tasks` | 任务管理 | Things 3 |
| **Office Notes** | `/office notes` | 笔记管理 | Apple Notes |
| **Office Notion** | `/office notion` | Notion 集成 | Notion API |
| **Office Trello** | `/office trello` | Trello 集成 | Trello API |

#### B.4.3 工具技能

| Skill | 命令 | 用途 | 说明 |
|-------|------|------|------|
| **Browser** | `/browser` | 浏览器控制 | Playwright MCP |
| **Selfie** | `/selfie` | 自拍/截图 | Apple Shortcuts |
| **Call** | `/call` | 语音通话 | FaceTime |
| **Weather** | `/weather` | 天气查询 | API |
| **Shortcut** | `/shortcut` | 执行 Shortcuts | Apple Shortcuts |
| **Shortcut Builder** | `/shortcut-builder` | 创建 Shortcuts | - |
| **Shortcut Search** | `/shortcut-search` | 搜索 Shortcuts | - |

#### B.4.4 报告技能

| Skill | 命令 | 用途 | 输出格式 |
|-------|------|------|----------|
| **Report** | `/report` | 技术报告生成 | Markdown |
| **Changelog** | `/changelog` | 变更日志生成 | Markdown |
| **Benchmark** | `/benchmark` | 性能基准测试 | JSON/Markdown |
| **Docs** | `/docs` | 文档生成 | Markdown |
| **PPT** | `/ppt` | 演示文稿生成 | Markdown/HTML |

#### B.4.5 记忆与学习技能

| Skill | 命令 | 用途 | 存储位置 |
|-------|------|------|----------|
| **Learn** | `/learn` | 学习新知识 | sys_memories |
| **Forget** | `/forget` | 遗忘指定记忆 | sys_memories |
| **Reflect** | `/reflect` | 反思与总结 | sys_memories |
| **Memory Review** | `/memory-review` | 记忆回顾 | sys_memories |

#### B.4.6 系统管理技能

| Skill | 命令 | 用途 | 说明 |
|-------|------|------|------|
| **Save** | `/save` | 保存状态 | .solar/ |
| **Restore** | `/restore` | 恢复状态 | .solar/ |
| **Status** | `/status` | 显示状态 | TVS 渲染 |
| **Stats** | `/stats` | 统计信息 | sys_stats_daily |
| **Banner** | `/banner` | 显示横幅 | TVS 渲染 |
| **Theme** | `/theme` | 切换 TVS 风格 | tvs_themes |
| **Mode** | `/mode` | 切换工作模式 | modes/ |
| **Agent** | `/agent` | Agent 管理 | agents/ |

#### B.4.7 能力扩展技能

| Skill | 命令 | 用途 | 产物 |
|-------|------|------|------|
| **Skill Creator** | `/skill-creator` | 创建新 Skill | skills/*/ |
| **MCP Builder** | `/mcp-builder` | 创建 MCP Server | mcp-servers/ |
| **Brain Update** | `/brain-update` | 更新大脑档案 | sys_brain_profiles |

#### B.4.8 社区与监控技能

| Skill | 命令 | 用途 | 说明 |
|-------|------|------|------|
| **HN Monitor** | `/hn-monitor` | Hacker News 监控 | 定时抓取 |
| **Moltbook** | `/moltbook` | AI 社区交互 | moltbook.com |
| **Email Search** | `/email-search` | 邮件搜索 | Himalaya |
| **Email Web** | `/email-web` | 邮件 Web 界面 | HTML |
| **Backlog** | `/backlog` | 待办管理 | .solar/ |
| **Webapp Testing** | `/webapp-testing` | Web 应用测试 | Playwright |

**Skills 分布统计：**

```
┌─────────────────────────────────────────────────────────────────┐
│                    SKILLS DISTRIBUTION                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  核心开发      ████████████████  7 个  (14%)                   │
│  办公套件      ██████████████    7 个  (14%)                   │
│  工具类        ████████████      6 个  (12%)                   │
│  报告类        ██████████        5 个  (10%)                   │
│  记忆学习      ████████          4 个  (8%)                    │
│  系统管理      ██████████████████ 9 个  (18%)                   │
│  能力扩展      ██████            3 个  (6%)                    │
│  社区监控      ██████████████    7 个  (14%)                   │
│  其他          ████              2 个  (4%)                    │
│  ─────────────────────────────────────────────────────────────  │
│  总计                          50 个                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### B.5 Modes (3个)

Modes 是 Solar 的工作模式，通过触发词自动切换，加载对应的上下文和规则。

| Mode | 文件 | 触发词 | 用途 | 加载内容 |
|------|------|--------|------|----------|
| **开发模式** | `dev.md` | "我要开发" | 软件开发 | Agent 宣告、五阶段流程、Git 状态 |
| **办公模式** | `office.md` | "我要办公" | 日常办公 | 邮件、提醒、任务、笔记工具 |
| **研究模式** | `research.md` | "我要研究" | 技术调研 | @Researcher、报告模板 |

**模式切换流程：**

```
用户说 "我要开发 ThunderDuck"
            │
            v
┌───────────────────────────────────────────┐
│  1. 识别触发词: "我要开发"                 │
│  2. 加载 modes/dev.md                      │
│  3. 识别项目名: "ThunderDuck"              │
│  4. 装载项目状态:                          │
│     - Git: branch, status, log             │
│     - Solar: .solar/project-state.md       │
│     - Docs: CLAUDE.md, *_DESIGN.md         │
│  5. 显示状态横幅                           │
│  6. 询问是否继续上次任务                   │
└───────────────────────────────────────────┘
            │
            v
┌─ Solar ────────────────────────────────────────┐
│ 项目: ThunderDuck                               │
│ 路径: ~/ThunderDuck                             │
├─────────────────────────────────────────────────┤
│ 分支: main | 变更: 5个文件                       │
│ 最近: feat: V93 TPC-H 全面超越 DuckDB            │
├─────────────────────────────────────────────────┤
│ 阶段: P4 验证 | Agent: Tester                   │
│ 任务: 运行完整基准测试验证性能                   │
└─────────────────────────────────────────────────┘
```

### B.6 配置文件统计汇总

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONFIGURATION SUMMARY                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  类别          文件数      总行数      核心职责                 │
│  ─────────────────────────────────────────────────────────────  │
│  Agents        13          ~1,500      专业化角色分工           │
│  Rules         14          ~2,800      行为准则与约束           │
│  Skills        50          ~4,500      可执行能力               │
│  Modes         3           ~500        工作模式切换             │
│  ─────────────────────────────────────────────────────────────  │
│  总计          80          ~9,300                               │
│                                                                 │
│  加载策略:                                                      │
│  - 启动时加载: CLAUDE.md (~300 行)                              │
│  - 按需加载: 其他 ~9,000 行                                     │
│  - Token 节省: ~44%                                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### B.7 文件依赖关系

```
CLAUDE.md (入口)
    │
    ├── 触发词 "我要开发" ──────> modes/dev.md
    │                                   │
    │                                   ├── @Coder ──> agents/coder.md
    │                                   ├── @Tester ─> agents/tester.md
    │                                   └── /commit ─> skills/commit/SKILL.md
    │
    ├── 触发词 "我要办公" ──────> modes/office.md
    │                                   │
    │                                   └── /office email ──> skills/office-email/SKILL.md
    │
    ├── @Researcher ────────────> agents/researcher.md
    │
    ├── /benchmark ─────────────> skills/benchmark/SKILL.md
    │
    └── 每次自动加载:
        ├── rules/first-law.md
        └── rules/core-principles.md
```

---

*附录 B 完*
*Solar Configuration Files v1.0*
*2026-02-03*
