# Solar 用户使用指南

> Solar 是一个 AI-native execution fabric：让用户当老板，让 AI 组织自己完成软件工程。

本指南面向公开仓库用户，和 README / install.sh / INSTALL-AGENT.md 保持一致。

---

## 1. Solar 是什么

Solar 当前由三层组成：

| 层级 | 范围 | 安装位置 | 说明 |
|---|---|---|---|
| L1 Solar Core | `CLAUDE.md`, `rules/`, `skills/`, `agents/`, `hooks/`, `core/` | `~/.claude/` + `~/.solar/` | Claude/Codex-native 工作流内核。 |
| L2 Solar Harness | `harness/` | `~/.solar/harness` + `~/.solar/bin/solar-harness` | 需求编译、Sprint 控制面、TaskGraph DAG、队列、租约、派发、评审。 |
| L2 optional components | `mempalace/`, `codex-bridge/` when present | `~/.solar/mempalace`, `~/.solar/codex-bridge` | 语义记忆与 Codex 协同协议，按仓库内容复制。 |
| Optional third-party skills | external repos | `~/.claude/skills/` | 可选增强。通过 `SKILLS-INSTALL.md` 安装，默认不自动装。 |

---

## 2. 快速安装

```bash
git clone https://github.com/suraj-subrahmanyan/OpenSolar.git ~/Solar
cd ~/Solar
./install.sh
```

`install.sh` 会执行：

1. 备份已有 `~/.claude/` 配置；
2. 复制 Solar Core 到 `~/.claude/`；
3. 创建 `~/.solar/`；
4. 同步仓库 `harness/` 到 `~/.solar/harness/`；
5. 创建 `~/.solar/bin/solar-harness`；
6. 如果仓库存在 `mempalace/`、`codex-bridge/`，则复制到 `~/.solar/`；
7. 运行 L1 + L2 自检。

安装成功的典型结尾：

```text
Solar L1 + L2 安装完成
```

---

## 3. 给 AI Agent 的安装方式

如果你希望 Claude、Codex、Cursor、Copilot 等 Agent 帮你安装，直接把下面的话交给它：

```text
Install Solar from https://github.com/suraj-subrahmanyan/OpenSolar using INSTALL-AGENT.md.
Before each command, report purpose, command, and expected output.
Do not use sudo/root. Stop on the first failure and show the exact output.
After install, verify L1 + L2 and run ~/.solar/bin/solar-harness help.
Do not install optional third-party skills unless I approve.
```

详细协议见：[`INSTALL-AGENT.md`](INSTALL-AGENT.md)。

---

## 4. 安装后自检

```bash
test -f ~/.claude/CLAUDE.md && \
test -d ~/.claude/rules && \
test -d ~/.claude/skills && \
test -d ~/.claude/agents && \
test -d ~/.solar/harness && \
test -x ~/.solar/harness/solar-harness.sh && \
test -L ~/.solar/bin/solar-harness && \
echo "Solar L1+L2 filesystem check PASS"
```

Harness CLI 自检：

```bash
~/.solar/bin/solar-harness help
```

重新同步 Harness runtime：

```bash
cd ~/Solar
./scripts/sync-harness-runtime.sh
~/.solar/bin/solar-harness help
```

---

## 5. 常用入口

| 入口 | 命令 / 文件 | 用途 |
|---|---|---|
| Solar Core | Claude Code 中输入 `solar` | 加载 Solar 工作流内核。 |
| Harness CLI | `~/.solar/bin/solar-harness help` | 查看 Harness 命令。 |
| Harness runtime | `~/.solar/harness/` | 本机运行目录。 |
| Harness source | `~/Solar/harness/` | 仓库发布源。 |
| Runtime sync | `~/Solar/scripts/sync-harness-runtime.sh` | 将仓库 Harness 同步到运行目录。 |
| Agent install | `INSTALL-AGENT.md` | 给 AI Agent 的安装/部署/自检协议。 |
| Optional skills | `SKILLS-INSTALL.md` | 可选第三方 skill packs 安装协议。 |

---

## 6. Skills 与插件

### Solar-bundled skills

仓库中的 `skills/` 会在安装时复制到：

```text
~/.claude/skills/
```

具体数量会随仓库变化，不要依赖固定数字。

### Optional third-party skills

第三方 skills 是增强，不是基础安装必需项。

规则：

- 不默认安装第三方仓库；
- 安装前必须问用户；
- 只在 `~/.claude/skills/` 下操作；
- 不删除用户已有 skills；
- 失败要报告，不假装成功。

见：[`SKILLS-INSTALL.md`](SKILLS-INSTALL.md)。

### Harness plugins

Harness 包含插件框架。插件必须位于：

```text
harness/plugins/<id>/manifest.yaml
```

并通过插件校验后，才应视为可用。公开仓库不默认承诺启用第三方插件。

---

## 7. 可选 API keys

安装不需要 API key。需要 API-backed 功能时：

```bash
cd ~/Solar
cp .env.template .env
# 编辑 .env，填入本机需要的 key
```

不要提交 `.env`。

---

## 8. Runtime 边界

| 类型 | 路径 | 是否应提交 |
|---|---|---|
| 仓库发布源 | `~/Solar/` | 是 |
| Harness 发布源 | `~/Solar/harness/` | 是 |
| 本机 runtime | `~/.solar/harness/` | 否 |
| runtime state | `run/`, `state/`, `logs/`, `cache/`, `vendor/`, `venvs/` | 否 |
| local env | `.env` | 否 |
| env template | `.env.template` | 是 |

---

## 9. Solar 的核心工作方式

Solar 的目标不是让用户手动操作多个 Agent，而是让用户当老板：

```text
用户给目标和边界
Solar 编译需求
Solar 生成 TaskGraph
Solar 调度物理算子
Solar 收集证据
Solar 评审结果
Solar 沉淀经验
Solar 逐步优化自己
```

关键原则：

- 自然语言是控制面；
- 需求是可编译 artifact；
- 模型不是唯一执行单位，AI-capable execution surface 才是执行单位；
- 并行需要依赖、写域、租约和评审边界；
- 没有证据，不算完成。

---

## 10. Troubleshooting

| 问题 | 检查 | 处理 |
|---|---|---|
| `solar` 在 Claude Code 中没反应 | `test -f ~/.claude/CLAUDE.md` | 重新运行 `cd ~/Solar && ./install.sh`，然后重启 Claude Code。 |
| `solar-harness` 不存在 | `ls -la ~/.solar/bin/solar-harness` | 运行 `cd ~/Solar && ./scripts/sync-harness-runtime.sh`。 |
| Harness CLI 报错 | `bash -n ~/.solar/harness/solar-harness.sh` | 把完整输出提交 issue。 |
| 缺少第三方 skill | `ls ~/.claude/skills` | 这是可选增强；按 `SKILLS-INSTALL.md` 安装。 |
| API 功能不可用 | `test -f ~/Solar/.env` | 从 `.env.template` 复制并在本机填写 key。 |

---

## 11. Issue 报告模板

```text
OS:
Shell:
Solar commit:
Command:
Expected:
Actual output:
Did INSTALL-AGENT.md pass? yes/no
Did ~/.solar/bin/solar-harness help pass? yes/no
```
