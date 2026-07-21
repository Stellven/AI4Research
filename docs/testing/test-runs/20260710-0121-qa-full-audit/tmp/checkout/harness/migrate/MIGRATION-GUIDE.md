# Solar Migration Guide

> 一键跨机迁移指南: MacBook → Mac Mini (或其他 macOS 机器)

## 快速开始

```bash
# 源机: 导出
solar-harness migrate export

# 传输 bundle 到目标机 (选一种)
scp ~/solar-bundles/solar-bundle-*.tar targetuser@targethost:~

# 目标机: 验证 + 导入
solar-harness migrate verify ~/solar-bundle-*.tar
solar-harness migrate import ~/solar-bundle-*.tar

# 目标机: 验证环境
solar-harness doctor
```

## 源机导出步骤

### 基本导出 (不含 secrets)

```bash
solar-harness migrate export
```

Bundle 输出到 `~/solar-bundles/solar-bundle-<hostname>-<date>.tar`

### 含 secrets 导出

```bash
# 通过参数传密码
solar-harness migrate export --include-secrets --password "your-password"

# 或交互式输入密码
solar-harness migrate export --include-secrets
```

Secrets 包含: SSH 私钥、GPG 密钥环、API keys、.env 文件

### 指定输出路径

```bash
solar-harness migrate export --out /Volumes/USB
```

## Bundle 传输建议

| 方式 | 命令 | 适用场景 |
|------|------|----------|
| **scp** | `scp bundle.tar targethost:~` | 网络直连 |
| **AirDrop** | Finder 拖拽 | 同网络 Mac |
| **USB** | `cp bundle.tar /Volumes/USB/` | 大文件离线 |
| **rsync** | `rsync -avP bundle.tar targethost:~` | 断点续传 |

> **注意**: Bundle 可能较大 (Solar DB + ChromaDB + Claude 配置 ≈ 500MB-2GB)

## 目标机预装清单

在 import 之前, 目标机必须安装:

```bash
# 1. Homebrew (如未装)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. bash 5+ (coordinator 依赖)
brew install bash

# 3. 基础工具
brew install tmux jq python3

# 4. Claude Code CLI
# 从 https://claude.ai/code 安装

# 5. (可选) import 时加 --install-deps 自动装回
```

### 跨架构注意 (Intel ↔ Apple Silicon)

- Intel → Apple Silicon: Homebrew 路径从 `/usr/local` → `/opt/homebrew`
- `brew bundle install` 会自动处理架构差异
- 部分 npm/pipx 包需重装原生依赖

## 目标机导入步骤

### 1. 验证 Bundle (可选但推荐)

```bash
solar-harness migrate verify ~/solar-bundle-*.tar
```

输出: SHA256 校验 + 文件完整性 + 路径替换模拟 + 依赖可装性

### 2. 预览导入 (dry-run)

```bash
solar-harness migrate import ~/solar-bundle-*.tar --dry-run
```

解到 `/tmp/migrate-dryrun-*`, 不改目标系统, 检查路径替换是否正确

### 3. 正式导入

```bash
# 基本导入
solar-harness migrate import ~/solar-bundle-*.tar

# 含 secrets
solar-harness migrate import ~/solar-bundle-*.tar --password "your-password"

# 自动安装依赖
solar-harness migrate import ~/solar-bundle-*.tar --install-deps
```

导入过程:
1. 自动备份目标机 `~/.solar` + `~/.claude` → `~/solar-backup-<ts>/`
2. 分阶段展开: 系统级 → Solar → Claude → Secrets
3. 自动路径替换 (`/Users/src_user/` → `/Users/dst_user/`)
4. 自动运行 `solar-harness doctor` 验证

### 4. 验证

```bash
# 环境检查
solar-harness doctor

# 启动 Solar
solar-harness start

# 验证数据
sqlite3 ~/.solar/solar.db "SELECT count(*) FROM sys_favorites;"
```

## 常见错误

### "bash 4+ 不可用"

```bash
brew install bash
# 重启终端或: exec /opt/homebrew/bin/bash
```

### "SHA256 不匹配"

Bundle 传输中损坏, 重新传输:

```bash
rsync -avP --checksum source:solar-bundle-*.tar ~
```

### "coordinator.sh 语法错误"

bash 版本不对, coordinator.sh 需要 bash 4+:

```bash
bash --version
brew install bash
```

### "Secrets 解密失败"

密码错误。确认与 export 时使用的密码一致。

### "tmux session 不存在"

导入后需手动启动:

```bash
solar-harness start
```

## 回滚

如果导入后有问题:

```bash
# 交互式回滚 (需确认)
solar-harness migrate rollback

# 自动确认
solar-harness migrate rollback --confirm
```

从最近的 `~/solar-backup-*/` 还原 `~/.solar` + `~/.claude`

## 安全注意事项

1. **secrets 默认不打包**: 需显式 `--include-secrets`
2. **AES-256 加密**: secrets 用 openssl AES-256-CBC 加密
3. **密码不落盘**: 只通过参数或 stdin 传入, 导入后 `unset`
4. **SSH 权限**: 展开后自动 `chmod 0600`
5. **Bundle 可验证**: verify 命令不解密 secrets 也能检查完整性
