# HIVE - Solar Community Neural Network

> Heterogeneous Intelligent Virtual Ecosystem
> 社区神经网络 - 多节点任务委托系统

## 概述

HIVE 是 Solar 的分布式任务执行引擎，允许多个 Solar 节点在局域网内自动发现、协作并共同完成任务。

**核心原则**: 不传参数、不传权重、只传任务

## Phase 2: 节点发现与通信 ✓

已实现功能:

- ✓ mDNS 服务发现 (自动发现局域网节点)
- ✓ P2P TCP 通信 (节点间消息传递)
- ✓ Coordinator 选举 (基于信誉+性能评分)
- ✓ 主备切换 (Coordinator 失效自动恢复)
- ✓ CLI 工具 (启动/管理节点)

## 快速开始

### 1. 启动第一个节点

```bash
bun core/hive/cli/node.ts start --name="节点1"
```

输出:
```
┌─ ☀️ HIVE Node ──────────────────────────────────────┐
│ Solar Community Neural Network                    │
└───────────────────────────────────────────────────┘

[HIVE] ✓ 节点启动成功: a1b2c3d4-...
[HIVE]   名称: 节点1
[HIVE]   层级: local
[HIVE]   能力: coder, tester, reviewer, docs, ops

[mDNS] ✓ 服务已发布: _solar-hive._tcp.local:9876
[P2P] ✓ 监听端口: 9876
[HIVE] ✓ 节点运行中... (Ctrl+C 退出)
```

### 2. 启动第二个节点 (另一台机器或另一个终端)

```bash
bun core/hive/cli/node.ts start --name="节点2" --port=9877
```

### 3. 查看发现的节点

```bash
bun core/hive/cli/node.ts peers
```

输出:
```
┌─ 🌐 Discovered Peers ──────────────────────────────┐
│ 已发现: 1 个节点
├─────────────────────────────────────────────────────┤
│ ✓ 节点1               192.0.2.4:9876
│   Tier: local | Agents: coder, tester, reviewer
└─────────────────────────────────────────────────────┘
```

### 4. 查看节点状态

```bash
bun core/hive/cli/node.ts status
```

## CLI 命令

### `start` - 启动节点

```bash
bun core/hive/cli/node.ts start [options]
```

**选项**:
- `--name=<名称>` - 节点名称 (默认: Solar-<hostname>)
- `--tier=<层级>` - 节点层级 (cloud/local/edge, 默认: local)
- `--port=<端口>` - 监听端口 (默认: 9876)
- `--agents=<列表>` - 能力列表 (逗号分隔)

**示例**:
```bash
# 基础启动
bun core/hive/cli/node.ts start

# 自定义名称和层级
bun core/hive/cli/node.ts start --name="我的节点" --tier=cloud

# 指定能力
bun core/hive/cli/node.ts start --agents=researcher,architect,coder
```

### `status` - 查看状态

```bash
bun core/hive/cli/node.ts status
```

### `peers` - 列出节点

```bash
bun core/hive/cli/node.ts peers
```

## Coordinator 选举

节点启动后会自动进行 Coordinator 选举，评分算法:

```
总分 = 信誉分 (40%) + 在线分 (30%) + 算力分 (20%) + 网络分 (10%)

信誉分: 基于任务成功率和积分余额
在线分: 基于在线时长和心跳新鲜度
算力分: 基于节点层级、能力数量和并发能力
网络分: 基于延迟和丢包率
```

**选举触发条件**:
- 节点启动 5 秒后首次选举
- 定期检查 (30 秒)
- Coordinator 下线
- 发现明显更优节点 (评分差 >20)

**Failover**:
- Coordinator 失效后自动切换到 Backup
- 无 Backup 时重新选举

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     HIVE Node                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  mDNS Discovery         P2P Transport                       │
│  ┌─────────────┐       ┌─────────────┐                     │
│  │ Advertise   │       │ TCP Server  │                     │
│  │ Browse      │       │ Socket Pool │                     │
│  └─────────────┘       └─────────────┘                     │
│                                                             │
│  Coordinator Election   Node Registry                      │
│  ┌─────────────┐       ┌─────────────┐                     │
│  │ Score Calc  │       │ Nodes       │                     │
│  │ Failover    │       │ Capabilities│                     │
│  └─────────────┘       └─────────────┘                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 测试

### 测试 mDNS 发现

```bash
bun core/hive/cli/test-discovery.ts mdns
```

### 测试 P2P 通信

```bash
bun core/hive/cli/test-discovery.ts p2p
```

## 技术细节

### mDNS 服务类型

```
服务类型: _solar-hive._tcp.local
默认端口: 9876

TXT 记录:
- nodeId: 节点唯一标识
- tier: 节点层级
- status: 节点状态
- capabilities: Agent 能力列表 (JSON)
- owner: 所有者
```

### P2P 消息格式

```typescript
interface HiveMessage {
  messageId: string;
  type: MessageType;
  from: string;
  to?: string;
  payload: T;
  timestamp: Date;
}
```

**消息类型**:
- `JOIN` - 节点加入网络
- `LEAVE` - 节点离开网络
- `HEARTBEAT` - 心跳 (30s 间隔)
- `TASK_OFFER` - 任务广播 (Phase 3)
- `BID` - 竞标 (Phase 3)
- `ASSIGN` - 任务分配 (Phase 3)
- `RESULT` - 结果返回 (Phase 3)

### 节点层级

| Tier | 算力 | 适合 Agent |
|------|------|-----------|
| **cloud** | 高 | Researcher, Architect, Reporter |
| **local** | 中 | Coder, Tester, Reviewer, Docs, Ops |
| **edge** | 低 | Secretary, SkillMarket |

## 下一步: Phase 3

- [ ] 任务市场 (Task Market)
- [ ] 竞标机制 (Bidding)
- [ ] 积分托管 (Escrow)
- [ ] 任务执行与验证

## 许可

MIT License

---

*HIVE - Solar Community Neural Network*
*命名者: 李卓远 (继承人)*
