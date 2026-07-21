# Solar 触发词速查表

> **快速查找你需要的命令** — 按场景分类

更新日期：2026-04-29

---

## 系统启动

| 触发词 | 效果 |
|--------|------|
| `solar` | 加载 Solar 系统，读取状态宣告 |
| `Solar-Max` | 切换到项目模式（五阶段流程 + 抗失忆） |
| `我要开发` | 进入开发模式（13 Agents + 五阶段） |
| `我要办公` | 进入办公模式（邮件/日程/文档） |
| `我要研究` | 调用 @Researcher 技术调研 |

---

## "我要..." 场景表

### 开发相关

| 你说 | Solar 做 |
|------|----------|
| "我要开发 xxx" | 切换开发模式，创建 Sprint |
| "我要实现 xxx 功能" | 委派建设者编码 |
| "我要写代码" | 调用编码技能 |
| "我要优化 xxx" | 性能分析和优化 |
| "我要重构 xxx" | 重构现有代码 |
| "我要测试 xxx" | 调用 @QA 或 /qa |
| "我要部署" | 调用部署技能或 /land-and-deploy |
| "我要发布" | 调用 /ship 发布流程 |

### 研究分析

| 你说 | Solar 做 |
|------|----------|
| "我要研究 xxx" | @Researcher 深度调研 |
| "我要分析 xxx" | 多专家会审分析 |
| "我要对比 xxx 和 yyy" | 对比分析 |
| "我要查资料" | 浏览器搜索 |
| "我要写论文" | academic-paper-composer |
| "我要做数据分析" | data-scientist 技能 |

### 设计规划

| 你说 | Solar 做 |
|------|----------|
| "我要设计 xxx" | architecture/design-systems |
| "我要写计划" | writing-plans |
| "我要做方案" | 调用规划者 |
| "我要头脑风暴" | brainstorming 技能 |
| "我要做架构图" | 生成架构设计 |

### 文档写作

| 你说 | Solar 做 |
|------|----------|
| "我要写文档" | technical-writer |
| "我要写 README" | 生成项目文档 |
| "我要整理笔记" | @Secretary |
| "我要写总结" | 生成总结报告 |

### 调试排查

| 你说 | Solar 做 |
|------|----------|
| "我要排查 xxx" | /investigate 根因分析 |
| "我要调试" | systematic-debugging |
| "我要查 bug" | 调试 + 分析 |
| "代码有问题" | /review 代码审查 |

---

## 批准和确认

| 触发词 | 效果 |
|--------|------|
| `批准` | 执行宣告中的请求 |
| `approved` | 同上（英文） |
| `好` | 确认，可能触发状态更新 |
| `OK` | 确认继续 |
| `可以` | 同意执行 |
| `确认` | 确认操作 |

---

## 模式切换

| 触发词 | 效果 |
|--------|------|
| `省钱` / `经济` | 切换到经济模式（GLM 优先，降低成本） |
| `用GLM` / `智谱` | 切换到 GLM 专用模式 |
| `平衡` / `正常` | 恢复平衡模式（Claude + GLM） |
| `谨慎` | 进入谨慎模式（/careful） |
| `守护` / `安全` | 进入守护模式（/guard） |
| `冻结` | 进入冻结模式（/freeze） |

---

## 洞察和分析

| 触发词 | 效果 |
|--------|------|
| `洞察分析：<主题>` | 快速洞察（3 专家会审，对话内完成） |
| `深入洞察 <主题>` | 完整报告（8 阶段 + 分章持久化） |
| `深度洞察：<主题>` | 强制深度研究（--force 跳过确认） |

---

## 计划和任务

| 触发词 | 效果 |
|--------|------|
| `/plan <任务>` | Plan-Act 执行任务 |
| `/plan preview <任务>` | 预览计划（不执行） |
| `/plan metrics` | 查看执行指标 |
| `/save` | 保存当前状态到 STATE.md |
| `/restore` | 从 STATE.md 恢复状态 |
| `/status` | 查看当前状态 |

---

## gstack 技能触发词

### 代码相关

| 触发词 | 技能 | 用途 |
|--------|------|------|
| `审查代码` / `review` | /review | 代码审查 |
| `QA` / `全面测试` / `找bug` | /qa | 质量保证 |
| `/qa-only` | /qa-only | 仅 QA，不修复 |
| `/investigate` / `排查` | /investigate | 根因分析 |
| `/benchmark` / `性能基准` | /benchmark | 性能测试 |
| `/autoreview` / `自动评审` | /autoplan | 自动评审 |

### 部署发布

| 触发词 | 技能 | 用途 |
|--------|------|------|
| `发布` / `上线` / `ship` | /ship | 发布部署 |
| `/land-and-deploy` | /land-and-deploy | 部署上线 |
| `/canary` | /canary | 金丝雀发布 |

### 网页相关

| 触发词 | 技能 | 用途 |
|--------|------|------|
| `浏览` / `打开网页` / `screenshot` | /browse | 网页浏览 |
| `/setup-browser-cookies` | /setup-browser-cookies | 设置 Cookies |

### 设计相关

| 触发词 | 技能 | 用途 |
|--------|------|------|
| `/design-review` | /design-review | 设计评审 |
| `/design-consultation` | /design-consultation | 设计咨询 |

### 其他

| 触发词 | 技能 | 用途 |
|--------|------|------|
| `/office-hours` | /office-hours | YC 办公模式 |
| `/careful` / `谨慎` | /careful | 谨慎模式 |
| `/guard` / `守护` | /guard | 守护模式 |
| `/freeze` / `冻结` | /freeze | 冻结模式 |
| `/unfreeze` | /unfreeze | 解冻 |
| `/retro` / `回顾` / `复盘` | /retro | 回顾会议 |
| `/cso` / `安全审计` | /cso | 安全审计 |

---

## Superpowers 技能触发词

### 规划和执行

| 触发词 | 技能 | 用途 |
|--------|------|------|
| `头脑风暴` / `brainstorm` / `创意` | brainstorming | 创意生成 |
| `写计划` / `制定计划` | writing-plans | 计划编写 |
| `执行计划` | executing-plans | 执行计划 |
| `/finishing-a-development-branch` | finishing | 收尾分支 |

### 开发流程

| 触发词 | 技能 | 用途 |
|--------|------|------|
| `TDD` / `测试驱动` | test-driven-development | 测试驱动开发 |
| `系统化调试` / `逐步排查` | systematic-debugging | 调试方法 |
| `/verification-before-completion` | verification | 完成前验证 |
| `/receiving-code-review` | receiving-review | 接收代码审查 |

### 其他

| 触发词 | 技能 | 用途 |
|--------|------|------|
| `/concise-planning` | concise-planning | 精简规划 |

---

## Agent 触发词

| 触发词 | 调用的 Agent | 用途 |
|--------|-------------|------|
| `@Dev` / `@Coder` | 开发者 | 代码实现 |
| `@QA` / `@Tester` | 测试工程师 | 质量保证 |
| `@Test` | 测试员 | 测试编写 |
| `@Write` / `@Docs` | 写作者 | 文档编写 |
| `@PM` | 产品经理 | 产品规划 |
| `@Secretary` | 秘书 | 记录整理 |
| `@Researcher` / `@Research` | 研究员 | 调研分析 |
| `@Architect` | 架构师 | 架构设计 |
| `@Reviewer` / `@Review` | 审查者 | 代码审查 |
| `@Ops` | 运维工程师 | 部署运维 |
| `@BenchmarkReporter` | 性能测试员 | 性能基准 |
| `@Guard` / `@Guardian` | 守护者 | 安全监控 |

---

## 小爱和 ML 实习生

| 触发词 | 效果 |
|--------|------|
| `小爱` / `呼叫小爱` | 远程 Mac mini 执行任务（邮件/日历/提醒） |
| `训练模型` / `微调` / `fine-tune` | 调用 ML 实习生（HuggingFace 任务） |
| `HuggingFace任务` | ML 实习生执行 |

---

## Codex 相关

| 触发词 | 效果 |
|--------|------|
| `/codex-plan` | Codex 制定计划 |
| `/codex-research` | Codex 深度研究 |
| `/codex` | 调用 Codex Pro (GPT-5.4) |

---

## Sprint 相关

| 触发词 | 效果 |
|--------|------|
| `开始 Sprint` | 创建新 Sprint |
| `查看 Sprint` | 查看当前 Sprint 状态 |
| `Sprint 状态` | 显示 Sprint 进度 |
| `完成 Sprint` | 标记 Sprint 完成 |

---

## 知识库相关

| 触发词 | 效果 |
|--------|------|
| `查 Cortex` | 查询 Cortex 知识库 |
| `查知识库` | 同上 |
| `查记忆` | 查询 MEMORY.md |
| `查教训` | 查询 Subconscious 教训 |
| `收藏` | 添加到 sys_favorites |

---

## 故障排查

| 触发词 | 效果 |
|--------|------|
| `诊断` | 运行系统诊断 |
| `健康检查` | kb-health-check |
| `doctor` | solar-harness doctor |
| `检查状态` | 查看系统状态 |

---

## 其他快捷触发

| 触发词 | 效果 |
|--------|------|
| `/commit` | Git commit |
| `/save` | 保存状态 |
| `/restore` | 恢复状态 |
| `/banner` | 显示欢迎横幅 |
| `/help` | 显示帮助信息 |

---

## 组合使用示例

| 你的输入 | 实际效果 |
|----------|----------|
| "我要开发登录功能，用 TDD" | 开发模式 + 测试驱动开发 |
| "洞察分析：微服务架构" | 3 专家会审微服务 |
| "review 这个 PR" | 代码审查技能 |
| "@QA 测试登录功能" | 调用 QA Agent |
| "我要部署，用 canary" | 金丝雀发布 |
| "careful 模式下发布" | 谨慎模式 + 发布 |
| "研究 React 性能优化" | @Researcher 调研 |
| "写计划：重构认证系统" | 生成重构计划 |

---

**提示**：大多数触发词支持中英文混用，Solar 会自动识别意图。

完整文档：[USER-GUIDE.md](./USER-GUIDE.md)
