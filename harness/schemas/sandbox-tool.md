# Sandbox Tool Interface Specification

> Version: 1.0-draft
> Sprint: sprint-20260416-154442 (D5 — 接口定义，不实现)
> 参考: Anthropic "Scaling Managed Agents: Decoupling the brain from the hands"

## 1. 设计目标

将 Claude 对文件系统和 Shell 的直接访问替换为通过 MCP 工具的间接调用，实现：

- **隔离**: 建设者的代码操作在沙盒内执行，不影响宿主系统
- **审计**: 所有文件/命令操作可追溯 (append-only event log)
- **可替换**: 沙盒可以是本地 Docker、远程 VM、或无操作 (dry-run)
- **安全**: 敏感路径 (凭证、配置) 需要显式授权

## 2. MCP 工具定义

### 2.1 sandbox.execute

在沙盒环境中执行命令。

```typescript
interface SandboxExecute {
  name: "sandbox.execute"

  input: {
    command: string        // 要执行的命令 (e.g., "bun test", "npm install")
    args?: string[]        // 命令参数 (可选, 用于安全转义)
    cwd?: string           // 工作目录 (默认: 项目根)
    env?: Record<string, string>  // 环境变量 (可选)
    timeout_ms?: number    // 超时 (默认: 60000, 最大: 600000)
  }

  output: {
    stdout: string         // 标准输出
    stderr: string         // 标准错误
    exit_code: number      // 退出码 (0=成功)
    duration_ms: number    // 执行耗时
    truncated: boolean     // 输出是否被截断
  }
}
```

**安全约束**:
- 禁止执行 `rm -rf /`、`sudo`、`curl | bash` 等高危命令
- 网络访问可配置 (默认允许 npm/pip, 禁止任意 HTTP)
- 超时强制 kill 子进程树

### 2.2 sandbox.read_file

在沙盒中读取文件内容。

```typescript
interface SandboxReadFile {
  name: "sandbox.read_file"

  input: {
    path: string           // 文件路径 (相对于项目根或绝对)
    encoding?: string      // 编码 (默认: "utf-8")
    range?: {              // 可选: 只读取部分内容
      start: number        // 起始行 (0-indexed)
      end: number          // 结束行 (不含)
    }
  }

  output: {
    content: string        // 文件内容
    encoding: string       // 实际编码
    size: number           // 文件大小 (bytes)
    lines: number          // 总行数
  }
}
```

**安全约束**:
- 禁止读取 `~/.ssh/`、`~/.aws/`、`.env` 等敏感路径
- 路径必须在项目白名单内 (由 coordinator 配置)
- 二进制文件返回 base64 编码

### 2.3 sandbox.write_file

在沙盒中写入文件。

```typescript
interface SandboxWriteFile {
  name: "sandbox.write_file"

  input: {
    path: string           // 文件路径
    content: string        // 写入内容
    mode?: "create" | "overwrite" | "append"  // 写入模式 (默认: overwrite)
    create_dirs?: boolean  // 是否自动创建父目录 (默认: false)
  }

  output: {
    bytes_written: number  // 写入字节数
    path: string           // 实际写入路径 (规范化后)
  }
}
```

**安全约束**:
- 禁止写入 `~/.ssh/`、`/etc/`、`/usr/` 等系统目录
- 禁止写入 `.env`、`credentials.json` 等凭证文件
- 单次写入上限 1MB

## 3. 未来替换路径

### Phase 1 (当前): 直通模式

```
Claude → sandbox.execute → 本地 Bash (无隔离)
Claude → sandbox.read_file → 本地 Read
Claude → sandbox.write_file → 本地 Write
```

Claude 直接使用 Bash/Read/Write 工具，sandbox-tool.md 仅作为规范。

### Phase 2: Docker 沙盒

```
Claude → MCP sandbox.execute → Docker exec <container>
Claude → MCP sandbox.read_file → docker cp <container>:path → stdout
Claude → MCP sandbox.write_file → stdin → docker cp - <container>:path
```

coordinator 启动时创建 Docker 容器，建设者所有操作在容器内执行。

### Phase 3: 远程沙盒

```
Claude → MCP sandbox.execute → gRPC → Remote VM
Claude → MCP sandbox.read_file → gRPC → Remote FS
Claude → MCP sandbox.write_file → gRPC → Remote FS
```

## 4. MCP Server 注册 (Phase 2+)

```json
// ~/.mcp.json
{
  "sandbox": {
    "command": "bun",
    "args": ["~/.solar/harness/sandbox-server.ts"],
    "env": {
      "SANDBOX_MODE": "docker",
      "SANDBOX_IMAGE": "solar-builder:latest",
      "PROJECT_ROOT": "~/..."
    }
  }
}
```

## 5. 权限模型

| 路径 | 读取 | 写入 | 执行 |
|------|------|------|------|
| 项目根/** | ✅ | ✅ | ✅ |
| ~/.solar/harness/** | ✅ | ✅ | ❌ |
| ~/.solar/reports/** | ✅ | ✅ | ❌ |
| ~/.claude/core/** | ✅ | ❌ | ❌ |
| ~/.ssh/** | ❌ | ❌ | ❌ |
| .env | ❌ | ❌ | ❌ |
| /etc/**, /usr/** | ❌ | ❌ | ❌ |

## 6. 事件审计

每个 sandbox 操作自动追加到 events.jsonl:

```jsonl
{"ts":"...","sid":"sprint-x","event":"sandbox_execute","by":"builder","data":{"command":"bun test","exit_code":0,"duration_ms":1200}}
{"ts":"...","sid":"sprint-x","event":"sandbox_write","by":"builder","data":{"path":"src/foo.ts","bytes_written":1024}}
```

## 7. 不在本 Sprint 范围

- 不实现 sandbox server (仅定义接口)
- 不实现 Docker 集成
- 不修改 Claude 工具调用链
- 不实现权限检查 (Phase 2 内容)
