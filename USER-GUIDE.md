# Solar 用户使用指南

> Solar 是一个 AI-native execution fabric：让用户当老板，让 AI 组织自己完成软件工程。

本指南是面向公开仓库用户的中文快速上手。完整、权威的安装文档是
[`INSTALL.md`](INSTALL.md)；架构与设计见 [`README.md`](README.md)。

---

## 1. 安装位置

Solar 安装为一个 Claude Code 内核覆盖层 + 一个运行时：

- `~/.claude/solar/` — 内核资产（生成的 `SOLAR.md`、rules/hooks/agents），命名空间隔离、可干净卸载。安装器**不会整体覆盖**你的 `~/.claude/CLAUDE.md`：它只在一个 sentinel 标记块内编辑，卸载时干净移除。
- `~/.solar/` — 运行时根目录（`install-receipt.json`、`config.env`、`.env`、`db/`、`bin/`，以及按所选组件的 `harness/`、`venv/`、`mempalace/` 等）。

---

## 2. 快速安装

```bash
git clone https://github.com/suraj-subrahmanyan/OpenSolar.git
cd OpenSolar
./install.sh
```

在终端里这是交互式安装（检测系统、解析组件选择、展示将要执行的操作并请你确认）。无人值守安装：

```bash
./install.sh --yes --components kernel,harness
```

默认选择 `kernel` + `harness`，在有 `bun` 时附带 `core-runtime`；其余组件默认关闭、按需选择。组件、参数、安装布局、按 Agent 安装等完整内容见 [`INSTALL.md`](INSTALL.md)；组件清单见 [`docs/COMPONENTS.md`](docs/COMPONENTS.md)。

---

## 3. 验证安装

```bash
~/.solar/bin/solar doctor --json     # 期望 "verdict": "ok"
claude                               # 首次打开时，批准一次性的 @~/.claude/solar/SOLAR.md 导入
```

---

## 4. 生命周期

所有生命周期操作通过 `~/.solar/bin/solar`：

```bash
solar doctor [--json]               # 健康 / 漂移检查
solar update [安装参数]             # 按 receipt 记录的组件重新运行安装
solar backup [--out FILE]           # 备份 config + secrets + receipt + db
solar restore <archive>             # 从备份恢复
solar components list               # 列出已安装组件
solar uninstall [--yes] [--keep-data] [--dry-run]
```

卸载详情见 [`docs/UNINSTALL.md`](docs/UNINSTALL.md)：receipt 驱动、无残留，`--keep-data` 保留数据库/配置/密钥。

---

## 5. 给 AI Agent 安装

如果你让 Claude、Codex、Cursor、Copilot 等 Agent 代为安装，要求它遵守协议：每条命令前报告 **目的 + 命令 + 预期输出**；不使用 `sudo`/root；首个失败即停止并展示原文；未经同意不安装第三方 skills；最后用 `~/.solar/bin/solar doctor --json` 验证。完整协议见 [`INSTALL.md`](INSTALL.md) 的 *Installing via an AI coding agent* 一节。

---

## 6. Skills

仓库自带 skills 由 `skills-*` 组件安装到 `~/.claude/skills/`。第三方 skill packs 是可选增强：单独安装、需先征得同意、只在 `~/.claude/skills/` 下操作、不覆盖你已有的 skills。

---

## 7. 可选 API keys

安装不需要 API key。需要 API-backed 功能时，把 `.env.template` 复制为本机 `.env` 并填入 key（不要提交 `.env`）。

---

## 8. Windows

原生（非 WSL）Windows 不在支持范围内；WSL2 是 Windows 的运行路径。从 PowerShell 运行 `install.ps1`，它会按需安装 WSL2（一次管理员批准 + 一次重启），再在 WSL 内运行 Linux 安装器并透传参数。详见 [`docs/WINDOWS.md`](docs/WINDOWS.md)。

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
| `solar` 在 Claude Code 中没反应 | 打开 `claude` | 批准一次性的 `@~/.claude/solar/SOLAR.md` 导入提示 |
| 组件被跳过（`core-runtime` / `skills-browser`） | `command -v bun` / `command -v cargo` | 安装对应依赖后用 `--components` 重新选择 |
| 组件提示需要某个配置值 | — | 用 `--set KEY=VALUE`（见该组件的 required vars） |
| 想先看将执行的操作 | — | `./install.sh --dry-run --components ...`（不写任何文件） |
| 全面健康检查 | — | `~/.solar/bin/solar doctor --json` |

---

## 11. Issue 报告模板

```text
OS:
Shell:
Solar commit:
Command:
Expected:
Actual output:
solar doctor --json verdict:
```
