# Solar Migration Manifest

> 迁移打包清单 — 按 5 类分组，每项标注用途/敏感度/必要性/路径

## (A) Solar 本体

| 路径 | 用途 | 敏感度 | 必要性 |
|------|------|--------|--------|
| `~/.solar/solar.db` | Cortex 结构化知识库 (SQLite) | 中 | 必须 |
| `~/.solar/harness/` | 协调器 + 人格 + 模板 + 脚本 | 低 | 必须 |
| `~/.solar/harness/coordinator.sh` | 协调器主循环 | 低 | 必须 |
| `~/.solar/harness/coordinator-watchdog.sh` | 看门狗 | 低 | 必须 |
| `~/.solar/harness/pane-launcher.sh` | Pane 启动器 | 低 | 必须 |
| `~/.solar/harness/start-incarnation.sh` | 化身启动 | 低 | 必须 |
| `~/.solar/harness/doctor.sh` | 环境自检 | 低 | 必须 |
| `~/.solar/harness/personas/` | 人格定义 (builder/evaluator/planner) | 低 | 必须 |
| `~/.solar/harness/templates/` | Sprint 模板 | 低 | 必须 |
| `~/.solar/harness/migrate/` | 迁移工具自身 | 低 | 必须 |
| `~/.solar/tests/harness/` | 回归测试 | 低 | 可选 |
| `~/.solar/harness/logs/` | 协调器日志 | 低 | 可选 |
| `~/.solar/harness/sprints/` | Sprint 历史 | 低 | 可选 |
| `~/.solar/reports/` | 报告输出 | 低 | 可选 |
| `~/.solar/rules-archive/` | 56 条历史铁律归档 | 低 | 可选 |
| `~/.solar/brain/` | Subconscious 教训库 | 低 | 必须 |
| `~/.solar/session-state.jsonl` | 会话状态日志 | 低 | 可选 |
| `~/.solar/owl/` | OWL 服务配置 | 低 | 可选 |
| `~/.solar/bin/solar-harness` | Harness CLI 入口 | 低 | 必须 |
| `~/.solar/bin/solar-intent` | 意图解析 CLI | 低 | 必须 |

### MemPalace (如存在)

| 路径 | 用途 | 敏感度 | 必要性 |
|------|------|--------|--------|
| `~/.solar/mempalace/` | MemPalace ChromaDB 存储 | 中 | 必须 |
| `~/.solar/mempalace/chroma.sqlite3` | ChromaDB 主库 | 中 | 必须 |

## (B) Claude 配置

| 路径 | 用途 | 敏感度 | 必要性 |
|------|------|--------|--------|
| `~/.claude/CLAUDE.md` | 全局指令 (Solar 人格+铁律) | 低 | 必须 |
| `~/.claude/rules/` | 铁律规则文件 (20+) | 低 | 必须 |
| `~/.claude/skills/` | 技能库 (Superpowers/gstack/ARIS) | 低 | 必须 |
| `~/.claude/hooks/` | Hook 脚本 | 低 | 必须 |
| `~/.claude/agents/` | Agent 定义 | 低 | 必须 |
| `~/.claude/settings.json` | 全局设置 (含 MCP server 配置) | 中 | 必须 |
| `~/.claude/settings.local.json` | 本地设置覆盖 | 中 | 必须 |
| `~/.claude/projects/<project>/memory/` | Claude Memory 持久记忆 | 中 | 必须 |
| `~/.claude/core/` | Solar 核心模块 (solar-farm/cortex/plan-act) | 低 | 必须 |
| `~/.claude/scripts/` | 辅助脚本 | 低 | 可选 |
| `~/.config/claude-code/` | Claude Code 配置 | 低 | 可选 |

## (C) 系统级

| 路径 | 用途 | 敏感度 | 必要性 |
|------|------|--------|--------|
| `~/.zshrc` | Zsh 配置 | 低 | 必须 |
| `~/.zprofile` | Zsh profile | 低 | 必须 |
| `~/.bashrc` | Bash 配置 | 低 | 可选 |
| `~/.bash_profile` | Bash profile | 低 | 可选 |
| `~/.tmux.conf` | Tmux 配置 | 低 | 必须 |
| `~/.gitconfig` | Git 全局配置 | 低 | 必须 |
| `~/Library/Application Support/Claude/claude_desktop_config.json` | Claude Desktop MCP 配置 | 中 | 必须 |
| `~/Library/LaunchAgents/com.solar.*` | Solar LaunchAgents | 低 | 可选 |
| `~/Library/LaunchAgents/com.anthropic.*` | Anthropic LaunchAgents | 低 | 可选 |

### crontab
- `crontab -l` 输出 (如有)

## (D) Secrets (需 --include-secrets, AES-256 加密分包)

| 路径 | 用途 | 敏感度 | 必要性 |
|------|------|--------|--------|
| `~/.ssh/id_*` | SSH 私钥 | **高** | 可选 |
| `~/.ssh/*.pem` | PEM 证书 | **高** | 可选 |
| `~/.ssh/*_rsa` | RSA 密钥 | **高** | 可选 |
| `~/.gnupg/` | GPG 密钥环 | **高** | 可选 |

### API Keys (从环境变量/shell rc 扫描)

| Key | 用途 | 敏感度 |
|-----|------|--------|
| `ANTHROPIC_API_KEY` | Claude API | **高** |
| `OPENAI_API_KEY` | OpenAI API | **高** |
| `DEEPSEEK_API_KEY` | DeepSeek API | **高** |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini API | **高** |
| `GLM_API_KEY` | 智谱 API | **高** |
| `OPENROUTER_API_KEY` | OpenRouter | **高** |

### .env 文件
- `~/.solar/.env` (如有)
- `~/.claude/.env` (如有)

## (E) 依赖快照 (export 自动生成)

| 文件 | 生成命令 | 用途 |
|------|----------|------|
| `deps/Brewfile` | `brew bundle dump --file=-` | Homebrew 依赖 |
| `deps/npm-global.txt` | `npm list -g --depth=0` | 全局 npm 包 |
| `deps/pipx.txt` | `pipx list --short` | pipx 工具 |
| `deps/pip-freeze.txt` | `python3 -m pip freeze` | Python 包 |

## 排除列表

以下路径**不打包**:

- `/tmp/`, `/var/tmp/`
- `~/Library/Caches/`
- `node_modules/`
- `__pycache__/`, `*.pyc`
- `.git/` (仓库数据)
- `tmux 临时 socket` (`/tmp/tmux-*`)
- `*.log` (日志文件, 可选排除)
- `.coordinator.pid`, `.watchdog.pid`, `.coordinator.lock` (运行时状态)
