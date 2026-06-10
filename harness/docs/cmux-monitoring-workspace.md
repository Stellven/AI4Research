# cmux 多标签四分屏 tmux 状态监控工作台

## 快速开始

```bash
# 1. 渲染（预览命令计划）
python3 scripts/cmux/render-cmux-workspace config/cmux-workspace-sample.yaml

# 2. 健康检查
python3 scripts/cmux/cmux-monitor-doctor config/cmux-workspace-sample.yaml

# 3. 启动工作台
python3 scripts/cmux/cmux-monitor-up config/cmux-workspace-sample.yaml

# 4. 停止工作台
python3 scripts/cmux/cmux-monitor-down config/cmux-workspace-sample.yaml
# or:
python3 scripts/cmux/cmux-monitor-down --name solar-runtime
```

## 脚本说明

| 脚本 | 职责 |
| --- | --- |
| `render-cmux-workspace` | 解析 workspace.yaml，校验 schema，输出 tab/pane 命令计划 |
| `cmux-monitor-up` | 调用 render，构建 cmux JSON layout，启动工作台 |
| `cmux-monitor-down` | 安全关闭工作台（不影响其他 cmux 会话） |
| `cmux-monitor-doctor` | 逐项检查 cmux/tmux/ssh/target/log，输出 machine-verifiable JSON |
| `tmux-pane-view` | capture-pane 轮询，显示 timestamp+host+target，fail-open |
| `tmux-pane-log-follow` | tail -F 模式，支持 local/remote，可校验 tmux target |

## Workspace Schema

```yaml
workspace_name: "my-workspace"

ssh_profiles:
  mini:
    host: "mini"
    user: "solar"
    control_master: true   # 开启 ControlMaster

tabs:
  - id: "tab-id"
    title: "Tab Title"
    layout: "quad"         # single | split | tri | quad
    panes:
      - title: "pane-name"
        source: "local"    # local | remote
        # ssh_profile: "mini"  # 仅 source=remote 时设置
        tmux_target: "session:window.pane"
        mode: "capture"    # capture | tail
        # log_path: "~/.logs/foo.log"  # 仅 mode=tail 时设置
        lines: 60          # capture 模式显示行数（可选，默认 60）
        interval_sec: 1    # capture 刷新间隔（可选，默认 1）
```

### 布局枚举

| layout | panes | 布局示意 |
| --- | --- | --- |
| `single` | 1 | full screen |
| `split` | 2 | 左右平分 |
| `tri` | 3 | 上两格 / 下一格 |
| `quad` | 4 | 2x2 等分（默认四分屏） |

### 约束

- 每 tab 最多 4 panes
- `mode=capture` 需要 `tmux_target`
- `mode=tail` 需要 `tmux_target` + `log_path`
- `source=remote` 需要 `ssh_profile`
- `source=local` 不允许 `ssh_profile`

## SSH 复用配置

在 `~/.ssh/config` 中添加：

```sshconfig
Host mini
  HostName your-mini.local
  User solar
  ControlMaster auto
  ControlPath ~/.ssh/cmux-%r@%h:%p
  ControlPersist 10m
  ServerAliveInterval 30
  ServerAliveCountMax 3
```

## Doctor 输出格式

```json
{
  "ok": false,
  "workspace": "solar-runtime",
  "checks": [
    {"name": "cmux_exists", "ok": true},
    {"name": "ssh_mini_connect", "ok": true},
    {"name": "tmux_target_solar_0_0", "ok": false, "reason": "target_not_found"}
  ]
}
```

`ok=false` 时 exit code 为 1，便于 CI/healthcheck 集成。

## Non-Goals（第一阶段）

1. 不做复杂 TUI 完美渲染
2. 不做可写交互控制面
3. 不重做 remote dispatch
4. 不把 cmux 工作台做成 remote tmux pane attach 协议层
