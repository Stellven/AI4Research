# Solar 资源清单 (Resource Inventory)

> 工欲善其事，必先利其器
> 最后更新: 2026-02-03

## 资源总览

| 类别 | 数量 | 说明 |
|------|------|------|
| 内置工具 | 14 | Claude Code 原生工具 |
| Skills | 49 | 命令式技能 |
| Agents | 15 | 智能体 |
| Hooks | 28 | 生命周期钩子 |
| 系统服务 | 10 | 后台服务 |
| Core 模块 | 27 | 核心代码模块 |
| 数据库表 | 115 | 系统表 |
| 数据库视图 | 83 | 查询视图 |
| 触发器 | 53 | 自动化触发器 |
| 规则文件 | 17 | 行为规范 |
| 模式 | 3 | 工作模式 |
| 模板 | 8 | 代码/文档模板 |
| 脚本 | 16+ | 自动化脚本 |
| **总计** | **430+** | |

---

## 1. 内置工具 (14)

| 工具 | 用途 | 常用场景 |
|------|------|----------|
| `Read` | 读取文件 | 代码分析、配置查看 |
| `Write` | 写入文件 | 创建新文件 |
| `Edit` | 编辑文件 | 精确修改代码 |
| `Bash` | 执行命令 | Git/npm/系统操作 |
| `Glob` | 文件搜索 | 按模式查找文件 |
| `Grep` | 内容搜索 | 代码搜索、定位 |
| `Task` | 子代理 | 并行任务、专项分析 |
| `WebFetch` | 网页抓取 | API调用、资料获取 |
| `WebSearch` | 网络搜索 | 查找资料、技术调研 |
| `LSP` | 语言服务 | 定义跳转、引用查找 |
| `TodoWrite` | 任务管理 | 任务规划、进度跟踪 |
| `NotebookEdit` | Jupyter编辑 | 数据分析 |
| `AskUserQuestion` | 用户交互 | 确认、选择 |
| `Skill` | 技能调用 | 执行已注册技能 |

---

## 2. Skills 技能 (49)

### 核心技能 (10)

| 技能 | 命令 | 用途 |
|------|------|------|
| Solar启动 | `/solar` | 五阶段开发模式 |
| Git提交 | `/commit` | 自动分析变更生成提交 |
| PR创建 | `/pr` | 创建Pull Request |
| 代码审查 | `/review` | 代码质量分析 |
| 项目构建 | `/build` | 构建项目 |
| 运行测试 | `/test` | 执行测试套件 |
| 状态保存 | `/save` | 保存会话状态 |
| 状态恢复 | `/restore` | 恢复会话状态 |
| 系统状态 | `/status` | 显示Solar状态 |
| 本体管理 | `/ontology` | 查看记忆和个性 |

### 办公技能 (12)

| 技能 | 命令 | 用途 |
|------|------|------|
| 办公模式 | `/office` | 启动办公助手 |
| 邮件CLI | `/office-email` | IMAP邮件客户端 |
| 邮件Web | `/email-web` | Web邮件界面 |
| 邮件搜索 | `/email-search` | 搜索邮件 |
| Apple Notes | `/office-notes` | 笔记管理 |
| Apple Reminders | `/office-reminders` | 提醒管理 |
| Things 3 | `/office-tasks` | 任务管理 |
| Notion | `/office-notion` | Notion集成 |
| Trello | `/office-trello` | Trello集成 |
| 电话/FaceTime | `/call` | 语音通话 |
| 拍照 | `/selfie` | 摄像头自拍 |

### 开发技能 (15)

| 技能 | 命令 | 用途 |
|------|------|------|
| 文档生成 | `/docs` | 生成/更新文档 |
| 技术报告 | `/report` | 撰写技术报告 |
| 变更日志 | `/changelog` | 生成CHANGELOG |
| 基准测试 | `/benchmark` | 性能测试 |
| 精确编辑 | `/precise-edit` | Grep→Read→Edit |
| MCP构建 | `/mcp-builder` | 创建MCP服务器 |
| 技能创建 | `/skill-creator` | 创建新Skill |
| 浏览器测试 | `/webapp-testing` | UI自动化测试 |
| 浏览器操作 | `/browser` | Playwright MCP |
| 阶段控制 | `/phase` | Solar阶段转换 |
| Token统计 | `/stats` | 使用量统计 |
| 横幅显示 | `/banner` | 显示启动横幅 |
| 主题切换 | `/theme` | TVS风格切换 |
| Agent列表 | `/agent` | 列出可用Agent |
| Skill市场 | `/skill-market` 或 `@SM` | 搜索/安装技能 |

### Apple Shortcuts (12)

| 快捷指令 | 用途 |
|----------|------|
| `solar_set_reminder` | 创建提醒 |
| `solar_get_weather` | 获取天气 |
| `solar_send_message` | 发送消息 |
| `solar_calendar_event` | 日历事件 |
| `solar_create_note` | 创建笔记 |
| `solar_take_photo` | 拍照 |
| `solar_control_homekit` | HomeKit控制 |
| `solar_clipboard` | 剪贴板操作 |
| `solar_location` | 获取位置 |
| `solar_screen_capture` | 屏幕截图 |
| `solar_open_app` | 打开应用 |
| `solar_siri_command` | Siri命令 |

---

## 3. Agents 智能体 (15)

### 云端Agent (需Opus, 5个)

| Agent | 触发 | 用途 | 单次Token |
|-------|------|------|-----------|
| 🔬 Researcher | `@Researcher` | 技术调研、可行性分析 | ~15,000 |
| 🏗️ Architect | `@Architect` | 架构设计、方案评审 | ~18,000 |
| 📝 Reporter | `@Reporter` | 长篇技术报告 | ~12,000 |
| 📊 BenchmarkReporter | `@BenchmarkReporter` | 性能测试报告 | ~10,000 |
| 📋 PM | `@PM` | 产品验收 | ~8,000 |

### 本地Agent (可Sonnet, 8个)

| Agent | 触发 | 用途 | 单次Token |
|-------|------|------|-----------|
| 💻 Coder | `@Coder` | 代码实现 | ~8,000 |
| 🧪 Tester | `@Tester` | 测试验证 | ~6,000 |
| 👁️ Reviewer | `@Reviewer` | 代码审查 | ~5,000 |
| 📖 Docs | `@Docs` | 文档生成 | ~4,000 |
| ⚙️ Ops | `@Ops` | 构建部署 | ~3,000 |
| 🛡️ Guard | `@Guard` | 规范检查 | ~3,000 |
| 🔍 Explore | Task工具 | 代码探索 | ~4,000 |
| 📐 Plan | Task工具 | 方案规划 | ~6,000 |

### 边缘Agent (可Haiku, 2个)

| Agent | 触发 | 用途 | 单次Token |
|-------|------|------|-----------|
| 📝 Secretary | `@Secretary` | 状态持久化 | ~2,000 |
| 🛒 SM | `@SM` | Skill市场 | ~2,500 |

---

## 4. MCP 服务器 (10)

| MCP | 用途 | 状态 |
|-----|------|------|
| `playwright` | 浏览器自动化 | ✅ 已配置 |
| `brain-router` | 多模型调度 | ✅ 已配置 |
| `himalaya` | 邮件访问 | ✅ 已配置 |
| `notion` | Notion API | ⚠️ 需配置 |
| `trello` | Trello API | ⚠️ 需配置 |
| `filesystem` | 文件系统 | ⚠️ 可选 |
| `github` | GitHub API | ⚠️ 可选 |
| `sqlite` | 数据库访问 | ⚠️ 可选 |
| `slack` | Slack集成 | ⚠️ 可选 |
| `discord` | Discord集成 | ⚠️ 可选 |

---

## 5. 数据库资源

### 核心系统表 (20)

| 表名 | 用途 |
|------|------|
| `sys_brain_profiles` | 大脑档案 |
| `sys_agents` | Agent注册 |
| `sys_skills` | Skill注册 |
| `sys_mcp_servers` | MCP配置 |
| `sys_shortcuts` | 快捷指令 |
| `sys_scripts` | 脚本缓存 |
| `sys_resources` | 资源索引 |
| `sys_quotas` | 配额管理 |
| `sys_preferences` | 系统偏好 |
| `sys_evolution_log` | 演进日志 |

### 本体表 (10)

| 表名 | 用途 |
|------|------|
| `ont_preference_dimensions` | 偏好维度 |
| `ont_learning_events` | 学习事件 |
| `ont_snapshots` | 本体快照 |
| `ont_reflection_log` | 反思日志 |

### 记忆表 (5)

| 表名 | 用途 |
|------|------|
| `evo_memory_episodic` | 情景记忆 |
| `evo_memory_semantic` | 语义记忆 |
| `evo_memory_procedural` | 程序记忆 |
| `evo_memory_links` | 记忆链接 |
| `evo_memory_graph` | 记忆图谱 |

### 统计表 (10)

| 表名 | 用途 |
|------|------|
| `sys_stats_daily` | 日统计 |
| `sys_invocation_stats` | 调用统计 |
| `sys_performance_log` | 性能日志 |
| `sys_cost_tracking` | 成本追踪 |

---

## 6. 规则文件 (17)

| 规则 | 文件 | 优先级 |
|------|------|--------|
| 第一规律 | `first-law.md` | 最高 |
| 监护人确认 | `guardian-confirm.md` | 最高 |
| 核心原则 | `core-principles.md` | 高 |
| IaST铁律 | `infrastructure-as-tables.md` | 高 |
| TVS渲染 | `tvs-rendering.md` | 高 |
| 能力演进 | `capability-evolution.md` | 高 |
| REE资源引擎 | `resource-execution-engine.md` | 高 |
| 性能测试 | `performance-testing.md` | 高 |
| Token效率 | `token-efficiency.md` | 中 |
| 编码规范 | `coding-standards.md` | 中 |
| 测试规范 | `testing.md` | 中 |
| 安全规范 | `security.md` | 中 |
| 文档规范 | `documentation.md` | 中 |

---

## 7. Core 模块 (27)

| 模块 | 路径 | 用途 |
|------|------|------|
| 本体系统 | `core/ontology/` | 记忆+个性 |
| 演进器 | `core/evolver/` | 自动演进 |
| TVS引擎 | `core/tvs/` | 终端渲染 |
| REE引擎 | `core/ree/` | 资源执行 |
| 快捷指令 | `core/shortcuts/` | Shortcuts集成 |
| 数据Agent | `core/data-agent/` | 数据分析 |
| 脚本引擎 | `core/script-engine/` | 脚本缓存执行 |

---

## 8. HIVE 协议资源 (规划中)

> 继承人命名: HIVE (Heterogeneous Intelligent Virtual Ecosystem)

### HIVE 消息类型

| 消息 | 用途 |
|------|------|
| `TASK_OFFER` | 任务广播 |
| `BID` | 能力竞标 |
| `ASSIGN` | 任务分配 |
| `RESULT` | 结果返回 |
| `VERIFY` | 结果验证 |
| `CREDIT` | 积分结算 |

### HIVE 核心原则

```
不传参数 ✗
不传权重 ✗
只传任务 ✓
```

---

## 任务分配检查清单

做任务分配前，检查以下资源:

- [ ] 有现成的 Skill 吗？ → 直接用
- [ ] 有现成的 Shortcut 吗？ → 优先用 (最快)
- [ ] 有缓存的 Script 吗？ → 复用
- [ ] 需要哪个 Agent？ → 按复杂度选
- [ ] 需要 MCP 吗？ → 检查是否已配置
- [ ] 需要新能力吗？ → 触发能力演进

---

*Solar Resource Inventory v1.0*
*工欲善其事，必先利其器*
