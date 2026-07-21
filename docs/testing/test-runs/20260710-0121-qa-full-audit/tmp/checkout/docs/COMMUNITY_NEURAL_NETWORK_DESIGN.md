# 小区神经网 (Community Neural Network) 完整设计

> 基于继承人李卓远的构想 | HIVE 协议 (蜂巢)
> 设计时间: 2026-02-04

---

## Executive Summary

**小区神经网**是一个创新的分布式 AI 协作系统，由继承人李卓远提出：
- **核心理念**: 一个小区多个设备运行 Solar，协同工作形成智能网络
- **协作方式**: 不传参数、不传权重、只传任务
- **协议名称**: **HIVE** (Heterogeneous Intelligent Virtual Ecosystem) - 蜂巢
- **潜力**: 20节点 × 38TOPS = 760TOPS (等效中型GPU服务器)

---

## 目录

1. [起源：继承人的构想](#1-起源继承人的构想)
2. [核心原则](#2-核心原则)
3. [系统架构](#3-系统架构)
4. [资源分析](#4-资源分析)
5. [HIVE 协议详解](#5-hive-协议详解)
6. [任务市场机制](#6-任务市场机制)
7. [先进经验借鉴](#7-先进经验借鉴)
8. [实现计划](#8-实现计划)
9. [PoC 原型](#9-poc-原型)

---

## 1. 起源：继承人的构想

### 1.1 原始提问

继承人李卓远提出三个核心问题：

1️⃣ **Solar 的 Multi-Agent 架构是否可以分布式部署？**
   - 分析不同 Agent 的资源消耗
   - 哪些能放在家庭设备（Mac mini）
   - 哪些需要云端

2️⃣ **一个小区多个设备如何协同？**
   - 多个 Mac mini 安装 Solar
   - 互相之间协同工作
   - 形成分布式网络

3️⃣ **协同不是参数共享，而是任务协同**
   - Publish - 发布任务
   - Interact - 交互协商
   - Bid - 竞标
   - Receive - 接收任务
   - Verify - 验证结果
   - Reward - 结算积分

### 1.2 继承人的洞察

**已保存的语义记忆** (2026-02-03):

```json
{
  "proposer": "李卓远 (继承人)",
  "lesson": "多个用户(如小区20户)的设备可以组成联邦网络，不传参数不传权重，只传任务，实现算力聚合",
  "protocol": "HIVE (Heterogeneous Intelligent Virtual Ecosystem)",
  "key_principles": [
    "不传参数(隐私)",
    "不传权重(太大)",
    "只传任务",
    "端到端加密",
    "积分激励"
  ],
  "potential": "20节点×38TOPS = 760TOPS，等效中型GPU服务器",
  "chinese_name": "蜂巢 / 社区智能蜂巢",
  "named_by": "李卓远 (继承人)"
}
```

**关键数据**:
- iPhone A19 ~75TOPS
- M4 ~38TOPS
- 边缘设备足够运行 8B-30B 参数模型

---

## 2. 核心原则

### 2.1 HIVE 五大原则

```
┌─────────────────────────────────────────────────────────────┐
│                    HIVE 核心原则                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1️⃣ 不传参数 (Privacy First)                                │
│     → 用户数据永不离开本地设备                              │
│     → 联邦学习思想，本地训练                                │
│                                                             │
│  2️⃣ 不传权重 (Lightweight Protocol)                         │
│     → 模型参数太大 (70B = 140GB)                            │
│     → 只传任务描述和结果 (<1KB)                             │
│                                                             │
│  3️⃣ 只传任务 (Task-Oriented)                                │
│     → 高层抽象: "帮我审查代码"                              │
│     → 而非底层: "运行这些命令"                              │
│                                                             │
│  4️⃣ 端到端加密 (Security)                                   │
│     → mTLS 双向认证                                         │
│     → AES-256-GCM 加密                                      │
│                                                             │
│  5️⃣ 积分激励 (Incentive)                                    │
│     → 贡献者获得积分                                        │
│     → 消费者支付积分                                        │
│     → 信誉系统防作恶                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 与其他系统的对比

| 系统 | 通信内容 | 优点 | 缺点 | HIVE 解决 |
|------|----------|------|------|----------|
| **联邦学习** | 梯度/参数 | 隐私保护 | 模型同构要求 | ✅ 只传任务，异构友好 |
| **Swarm AI** | 状态向量 | 分布式智能 | 中心化调度 | ✅ 去中心化竞标 |
| **区块链** | 交易数据 | 去中心化 | 性能瓶颈 | ✅ 轻量共识 |
| **Actor 模型** | 消息 | 容错性强 | 单机为主 | ✅ 跨设备扩展 |
| **MicroServices** | HTTP/RPC | 松耦合 | 网络开销 | ✅ LAN优先 |

---

## 3. 系统架构

### 3.1 四层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    HIVE 四层架构                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Layer 4: 应用层 (Application)                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  • Task Market - 任务市场                                    │  │
│  │  • Agent Pool - Agent 池                                     │  │
│  │  • Credit Ledger - 积分账本                                  │  │
│  │  • Knowledge Sharing - 知识共享 (内容寻址)                   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Layer 3: 编排层 (Orchestration)                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  • Task Scheduler - 任务调度                                 │  │
│  │  • Bidding Engine - 竞标引擎                                 │  │
│  │  • Verifier - 结果验证                                       │  │
│  │  • Incentive Engine - 激励引擎                               │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Layer 2: 网络层 (Network)                                          │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  • Discovery (mDNS + Tailscale) - 节点发现                   │  │
│  │  • Routing (Hybrid Topology) - 混合路由                      │  │
│  │  • Sync (CRDT) - 状态同步                                    │  │
│  │  • Security (mTLS) - 安全通信                                │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Layer 1: 传输层 (Transport)                                        │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  • LAN (mDNS) - 局域网直连                                   │  │
│  │  • Tunnel (Tailscale) - NAT穿透                              │  │
│  │  • Relay (WebSocket) - 中继连接                              │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 网络拓扑

采用 **动态混合拓扑** (Hub-Spoke + Mesh):

```
┌─────────────────────────────────────────────────────────────────────┐
│              HIVE 动态混合拓扑                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                    ┌──────────────────┐                             │
│                    │   Coordinator    │  ← 动态选举                 │
│                    │  (Mac Studio)    │     (信誉最高)               │
│                    └────────┬─────────┘                             │
│                             │                                       │
│         ┌───────────────────┼───────────────────┐                   │
│         │                   │                   │                   │
│         ▼                   ▼                   ▼                   │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐           │
│  │  Worker 1   │◀───▶│  Worker 2   │◀───▶│  Worker 3   │           │
│  │ Mac mini M2 │     │ Mac mini M2 │     │ Intel NUC   │           │
│  │  🟡 Local   │     │  🟡 Local   │     │  🟡 Local   │           │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘           │
│         │                   │                   │                   │
│  ┌──────┴──────┐     ┌──────┴──────┐     ┌──────┴──────┐           │
│  │   Cache 1   │     │   Cache 2   │     │   Cache 3   │           │
│  │  RPi 4B     │     │  旧 MacBook │     │  RPi 5      │           │
│  │  🟢 Edge    │     │  🟢 Edge    │     │  🟢 Edge    │           │
│  └─────────────┘     └─────────────┘     └─────────────┘           │
│                                                                     │
│  图例:                                                              │
│  ─────── Hub-Spoke (Coordinator ↔ Worker)                          │
│  ◀─────▶ Mesh P2P (Worker ↔ Worker)                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**小区场景示例** (20户家庭):
- 10 户有 Mac mini M2 (Worker)
- 5 户有旧设备 (Edge Cache)
- 3 户有高性能工作站 (候选 Coordinator)
- 2 户仅使用移动设备 (Consumer)

---

## 4. 资源分析

### 4.1 Solar 组件资源消耗

**完整分析报告**: `docs/DISTRIBUTED_DEPLOYMENT_ANALYSIS.md`

**关键发现**:

| 组件 | 数量 | 可离线运行 | 主要瓶颈 |
|------|------|-----------|----------|
| Agents | 15 | 0 (全依赖LLM) | Token成本 + 网络 |
| Skills | 49 | 35+ | 部分需网络API |
| MCP Servers | 10 | 2 (filesystem, sqlite) | Playwright (500MB内存) |
| Shortcuts | 12 | 8 | 部分需联网 |

### 4.2 设备分级部署

| 设备级别 | 硬件规格 | 可运行组件 | Token成本/天 |
|----------|---------|-----------|-------------|
| 🟢 **边缘** (RPi 4B) | 4GB RAM, 32GB | Secretary, SM + 20+ Skills | ~$0.05 |
| 🟡 **本地** (Mac mini M2) | 16GB RAM, 256GB | 8 Local Agents + 全部 Skills | ~$0.50 |
| 🔴 **云端** (Mac Studio) | 64GB+ RAM, 1TB | 全部15 Agents | ~$5.00 |

**本地 LLM 选项**:
- Qwen2.5-3B (4GB VRAM) → 替代 Haiku
- Qwen2.5-14B (12GB VRAM) → 替代 Sonnet
- Qwen2.5-72B (48GB VRAM) → 替代 Opus

---

## 5. HIVE 协议详解

### 5.1 协议栈

```
┌─────────────────────────────────────────────────────────────────────┐
│                      HIVE PROTOCOL STACK                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Layer 5: Application Protocol                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  TaskMarket Protocol - 任务发布/竞标/验证                     │  │
│  │  Knowledge Protocol - 知识共享/缓存                          │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Layer 4: Coordination Protocol                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Scheduler Protocol - 任务调度与路由                         │  │
│  │  Consensus Protocol - 轻量共识 (信誉加权BFT)                 │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Layer 3: Sync Protocol                                             │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  CRDT Sync - 无冲突状态同步                                  │  │
│  │  Git Sync - 代码仓库同步                                     │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Layer 2: Discovery & Routing                                       │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  mDNS - 局域网零配置发现                                     │  │
│  │  Tailscale - 跨子网虚拟组网                                  │  │
│  │  Bootstrap - 可选中心注册                                    │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Layer 1: Transport & Security                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  TCP/QUIC - 传输协议                                         │  │
│  │  mTLS - 双向TLS认证                                          │  │
│  │  AES-256-GCM - 数据加密                                      │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 消息格式

**HIVE Message Protocol** (JSON-RPC 2.0 扩展):

```typescript
interface HiveMessage {
  version: "1.0";
  type: "task" | "bid" | "result" | "verify" | "credit";

  // 消息元数据
  messageId: string;
  timestamp: string;
  from: string;  // 发送节点 ID
  to?: string;   // 接收节点 ID (可选, broadcast 时为空)

  // 消息内容
  payload: TaskPayload | BidPayload | ResultPayload | VerifyPayload | CreditPayload;

  // 安全
  signature: string;  // Ed25519 签名
  nonce: string;
}

// 任务消息
interface TaskPayload {
  taskId: string;
  description: string;  // 自然语言描述
  requirements: {
    requiredAgents: string[];     // 需要的 Agent: ["coder", "tester"]
    minTier: "edge" | "local" | "cloud";
    maxDurationMs: number;
    maxTokens: number;
  };
  reward: number;  // 积分奖励
  deadline: string;
}

// 竞标消息
interface BidPayload {
  taskId: string;
  bidder: string;   // 节点 ID
  estimate: {
    durationMs: number;
    tokens: number;
    confidence: number;  // 0-1
  };
  price: number;  // 要求的积分
}

// 结果消息
interface ResultPayload {
  taskId: string;
  success: boolean;
  output: string;
  artifacts?: string[];  // 产物文件 CID (内容寻址)
  metrics: {
    durationMs: number;
    tokensUsed: number;
    memoryPeakMB: number;
  };
}

// 验证消息
interface VerifyPayload {
  taskId: string;
  resultId: string;
  verifier: string;  // 验证者节点 ID
  approved: boolean;
  confidence: number;
}

// 积分消息
interface CreditPayload {
  transactionId: string;
  from: string;
  to: string;
  amount: number;
  reason: string;  // "task_reward" | "verification_fee"
  taskId?: string;
}
```

---

## 6. 任务市场机制

### 6.1 完整流程

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          TASK MARKET WORKFLOW                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  PHASE 1: PUBLISH (发布)                                                        │
│  ────────────────────────────────────────────────────────────────────────      │
│                                                                                 │
│    用户: "@Coder 优化这个函数性能"                                               │
│       │                                                                         │
│       ▼                                                                         │
│    ┌─────────────────────────────────────────────────────────────────────┐     │
│    │  本地 Solar 解析:                                                    │     │
│    │  • 检查本地能力: Coder Agent 可用? 负载如何?                         │     │
│    │  • 决策: 本地执行 vs 发布到网络                                      │     │
│    └─────────────────────────────────────────────────────────────────────┘     │
│       │                                                                         │
│       │ (假设本地繁忙, 发布到网络)                                              │
│       ▼                                                                         │
│    ┌─────────────────────────────────────────────────────────────────────┐     │
│    │  广播任务到 HIVE:                                                    │     │
│    │  {                                                                   │     │
│    │    taskId: "task-001",                                               │     │
│    │    description: "优化函数性能",                                      │     │
│    │    requirements: { agents: ["coder"], tier: "local" },              │     │
│    │    reward: 100,  // 积分                                             │     │
│    │    deadline: "5min"                                                  │     │
│    │  }                                                                   │     │
│    └─────────────────────────────────────────────────────────────────────┘     │
│       │                                                                         │
│       │ mDNS 广播到局域网所有节点                                               │
│       ▼                                                                         │
│                                                                                 │
│  ──────────────────────────────────────────────────────────────────────────    │
│  PHASE 2: INTERACT & BID (交互与竞标)                                           │
│  ──────────────────────────────────────────────────────────────────────────    │
│                                                                                 │
│    节点 A (Mac mini #1)    节点 B (Mac mini #2)    节点 C (NUC)                │
│       │                        │                        │                      │
│       │ 收到任务               │ 收到任务               │ 收到任务              │
│       ▼                        ▼                        ▼                      │
│    检查能力                 检查能力                检查能力                    │
│    • Coder ✓                • Coder ✓               • Coder ✓                 │
│    • 负载 30%               • 负载 70%              • 负载 10%                 │
│    • 信誉 85                • 信誉 75               • 信誉 90                  │
│       │                        │                        │                      │
│       ▼                        ▼                        ▼                      │
│    计算竞标价格             计算竞标价格            计算竞标价格                │
│    • 估计耗时 3min          • 估计耗时 4min         • 估计耗时 2.5min          │
│    • 要求积分 80            • 要求积分 90           • 要求积分 75              │
│       │                        │                        │                      │
│       ▼                        ▼                        ▼                      │
│    发送 BID                 发送 BID                发送 BID                   │
│       │                        │                        │                      │
│       └────────────────────────┴────────────────────────┘                      │
│                                 │                                              │
│                                 ▼                                              │
│                         ┌──────────────┐                                       │
│                         │ 发布者评估所有BID │                                   │
│                         │ 选择最优: 节点C  │  (信誉90, 价格75, 耗时2.5min)     │
│                         └──────┬───────┘                                       │
│                                │                                               │
│                                ▼                                               │
│                         发送 ACCEPT 给节点C                                     │
│                                                                                 │
│  ──────────────────────────────────────────────────────────────────────────    │
│  PHASE 3: RECEIVE & EXECUTE (接收与执行)                                        │
│  ──────────────────────────────────────────────────────────────────────────    │
│                                                                                 │
│                            节点 C (NUC)                                         │
│                                 │                                              │
│                                 ▼                                              │
│                         收到 ACCEPT                                             │
│                                 │                                              │
│                                 ▼                                              │
│                         ┌──────────────┐                                       │
│                         │   沙箱执行    │                                       │
│                         │  Coder Agent │                                       │
│                         │  (隔离环境)  │                                       │
│                         └──────┬───────┘                                       │
│                                │                                               │
│                                ▼                                               │
│                         记录度量数据:                                           │
│                         • 实际耗时 2.8min                                       │
│                         • Token 7,500                                          │
│                         • 内存峰值 380MB                                        │
│                                │                                               │
│                                ▼                                               │
│                         返回 RESULT                                             │
│                                                                                 │
│  ──────────────────────────────────────────────────────────────────────────    │
│  PHASE 4: VERIFY (验证)                                                         │
│  ──────────────────────────────────────────────────────────────────────────    │
│                                                                                 │
│    发布者 (原节点)                                                              │
│       │                                                                         │
│       ▼                                                                         │
│    收到 RESULT                                                                  │
│       │                                                                         │
│       ▼                                                                         │
│    ┌─────────────────────────────────────────────────────────────────────┐     │
│    │  验证策略选择:                                                       │     │
│    │                                                                      │     │
│    │  • Simple Task → Self Verify (自己检查)                              │     │
│    │  • Code Task → Deterministic Verify (运行测试)                       │     │
│    │  • High Value → Peer Verify (请其他节点复核)                         │     │
│    │  • Critical → Consensus Verify (多数节点确认)                        │     │
│    └─────────────────────────────────────────────────────────────────────┘     │
│       │                                                                         │
│       │ (代码优化任务 → 运行测试验证)                                           │
│       ▼                                                                         │
│    执行测试套件:                                                                │
│    • 功能测试 PASS ✓                                                            │
│    • 性能测试 PASS ✓ (提升 15%)                                                 │
│    • 回归测试 PASS ✓                                                            │
│       │                                                                         │
│       ▼                                                                         │
│    广播 VERIFY 消息                                                             │
│    { approved: true, confidence: 0.95 }                                         │
│                                                                                 │
│  ──────────────────────────────────────────────────────────────────────────    │
│  PHASE 5: REWARD (奖励)                                                         │
│  ──────────────────────────────────────────────────────────────────────────    │
│                                                                                 │
│    ┌─────────────────────────────────────────────────────────────────────┐     │
│    │  积分结算:                                                           │     │
│    │                                                                      │     │
│    │  发布者 → 节点C:  75 积分 (任务奖励)                                 │     │
│    │  发布者 → 验证者:  5 积分 (验证费用, 如果有peer verify)              │     │
│    │                                                                      │     │
│    │  更新信誉:                                                           │     │
│    │  • 节点C 信誉 90 → 92 (任务成功+1, 质量优+1)                         │     │
│    │  • 节点C 累计贡献 +1                                                 │     │
│    └─────────────────────────────────────────────────────────────────────┘     │
│       │                                                                         │
│       ▼                                                                         │
│    写入 Credit Ledger (CRDT Append-Only Log)                                    │
│    {                                                                            │
│      txId: "tx-001",                                                            │
│      from: "node-publisher",                                                    │
│      to: "node-C",                                                              │
│      amount: 75,                                                                │
│      taskId: "task-001",                                                        │
│      timestamp: "2026-02-04T06:00:00Z"                                          │
│    }                                                                            │
│                                                                                 │
│    全网同步 (Gossip 协议, <5s 达到最终一致性)                                   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 竞标算法

```typescript
interface BidCalculation {
  nodeId: string;
  capability: number;      // 0-1, 能力匹配度
  load: number;            // 0-1, 负载 (反向)
  reputation: number;      // 0-100
  estimatedDuration: number;
  estimatedTokens: number;
  price: number;           // 要求的积分
}

class BiddingEngine {
  calculateBid(task: HiveTask, node: HiveNode): BidCalculation {
    // 1. 能力匹配
    const capability = this.matchCapability(task, node);
    if (capability < 0.7) {
      return null;  // 能力不足，不竞标
    }

    // 2. 负载评估
    const load = 1 - (node.currentLoad / node.maxLoad);
    if (load < 0.2) {
      return null;  // 负载过高，不竞标
    }

    // 3. 估算资源消耗
    const estimatedDuration = this.estimateDuration(task, node);
    const estimatedTokens = this.estimateTokens(task);

    // 4. 计算报价
    const basePrice = task.reward * 0.7;  // 70% 底价
    const loadPremium = (1 - load) * 20;  // 负载高加价
    const urgencyPremium = this.isUrgent(task) ? 30 : 0;
    const price = basePrice + loadPremium + urgencyPremium;

    // 5. 竞争力评分 (给发布者选择用)
    const competitiveness =
      capability * 0.4 +
      load * 0.3 +
      (node.reputation / 100) * 0.2 +
      (1 - price / task.reward) * 0.1;

    return {
      nodeId: node.nodeId,
      capability,
      load,
      reputation: node.reputation,
      estimatedDuration,
      estimatedTokens,
      price,
      competitiveness,  // 内部使用
    };
  }

  selectWinner(bids: BidCalculation[]): string {
    // 发布者选择策略：综合评分最高
    const scored = bids.map(bid => ({
      nodeId: bid.nodeId,
      score: this.calculateBidScore(bid),
    }));

    scored.sort((a, b) => b.score - a.score);
    return scored[0]?.nodeId;
  }

  private calculateBidScore(bid: BidCalculation): number {
    // 综合评分 = 能力 40% + 信誉 30% + 价格 20% + 速度 10%
    return (
      bid.capability * 40 +
      (bid.reputation / 100) * 30 +
      (1 - bid.price / 200) * 20 +  // 归一化价格
      (1 - bid.estimatedDuration / 600000) * 10  // 归一化时长
    );
  }
}
```

### 6.3 积分经济模型

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            CREDIT ECONOMICS                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  初始积分分配:                                                                   │
│  ────────────────────────────────────────────────────────────────────────      │
│  • 新节点加入: 100 积分 (初始信用)                                              │
│  • 贡献设备: +50 积分/月 (激励参与)                                             │
│  • 推荐新节点: +20 积分 (网络增长)                                              │
│                                                                                 │
│  任务定价:                                                                      │
│  ────────────────────────────────────────────────────────────────────────      │
│  • 轻量任务 (Secretary, SM): 5-10 积分                                          │
│  • 中等任务 (Coder, Reviewer): 30-80 积分                                       │
│  • 重量任务 (Researcher, Architect): 100-200 积分                               │
│  • 紧急任务: +50% 加价                                                          │
│                                                                                 │
│  积分流转:                                                                      │
│  ────────────────────────────────────────────────────────────────────────      │
│   用户消费 (发布任务)                                                           │
│         │                                                                       │
│         ▼                                                                       │
│   ┌──────────────────────────────────────────────────────────────────┐         │
│   │                    Escrow (托管)                                  │         │
│   │   Task发布时锁定奖励积分，防止跑路                                 │         │
│   └────────────┬─────────────────────────────────┬───────────────────┘         │
│                │ 验证通过                         │ 验证失败/超时              │
│                ▼                                 ▼                             │
│         ┌────────────┐                      ┌────────────┐                     │
│         │  Worker    │                      │ 退回发布者 │                     │
│         │  获得奖励  │                      │ 扣除手续费 │                     │
│         └────────────┘                      └────────────┘                     │
│                │                                                                │
│                ▼                                                                │
│   ┌──────────────────────────────────────────────────────────────────┐         │
│   │              Credit Ledger (积分账本)                             │         │
│   │   • CRDT Append-Only Log (无冲突同步)                             │         │
│   │   • 全网可审计                                                    │         │
│   │   • 防篡改 (链式哈希)                                             │         │
│   └──────────────────────────────────────────────────────────────────┘         │
│                                                                                 │
│  防作恶机制:                                                                    │
│  ────────────────────────────────────────────────────────────────────────      │
│  • 恶意结果 → 扣除积分 + 信誉降级                                               │
│  • 长期离线 → 信誉衰减 (每7天 -5%)                                              │
│  • 负积分节点 → 只能贡献不能消费 (赚回正数)                                     │
│  • 信誉 <30 → 自动隔离                                                          │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 6.4 验证策略

| 任务类型 | 验证方式 | 验证者 | 成本 |
|----------|---------|--------|------|
| 简单查询 | Self | 发布者 | 0 |
| 代码实现 | Deterministic (测试) | 自动化 | 0 |
| 代码审查 | Peer | 另一个 Reviewer | 5 积分 |
| 架构设计 | Consensus | 3个 Architect | 15 积分 |
| 数据分析 | Peer + Deterministic | Reviewer + 测试 | 10 积分 |

---

## 7. 先进经验借鉴

### 7.1 调研总结

**已调研系统** (详见 @Researcher 报告):

1. **联邦学习** (Google/Apple)
   - 借鉴: 数据不出设备、本地训练
   - 适配: HIVE 不传参数原则

2. **DMAS** (去中心化多Agent群)
   - 借鉴: 拜占庭容错、PSO调度
   - 适配: 恶意节点检测

3. **IPFS** (内容寻址存储)
   - 借鉴: CID哈希、BitSwap协议
   - 适配: 知识共享去重

4. **Actor模型** (Akka/Erlang)
   - 借鉴: 监督树、Let it Crash
   - 适配: 容错恢复机制

5. **OpenAI Swarm**
   - 借鉴: Handoff 轻量转移
   - 适配: 任务委托协议

6. **CrewAI**
   - 借鉴: 层级委托、Manager选举
   - 适配: Coordinator 角色

7. **PBFT 变体**
   - 借鉴: 信誉加权共识
   - 适配: 轻量投票机制

### 7.2 技术选型

| 模块 | 选型 | 开源库 | 理由 |
|------|------|--------|------|
| 节点发现 | mDNS | Bonjour/Avahi | 局域网零配置 |
| 虚拟组网 | Tailscale | tailscale.com | NAT穿透简单 |
| 消息传播 | GossipSub | libp2p | 成熟稳定 |
| 状态同步 | CRDT | yjs/automerge | 无冲突合并 |
| Agent 协作 | Swarm-style | 自研 | 轻量定制 |
| 任务调度 | PSAS改进 | 自研 | 预测+匹配 |
| 容错 | Actor 监督树 | 自研 | 契合 Solar |
| 积分账本 | Append-Only Log | SQLite CRDT | 简单高效 |

---

## 8. 实现计划

### 8.1 Phase 1: Foundation (已完成 ✅)

**Week 1-2**:
- ✅ HIVE Protocol 类型定义 (`core/hive/types.ts`)
- ✅ 节点注册与管理 (`core/hive/node.ts`)
- ✅ 任务调度器 (`core/hive/scheduler.ts`)
- ✅ 积分系统 (`core/hive/credits.ts`)
- ✅ 数据库 Schema (`core/hive/schema.sql`)

**成果**: HIVE 核心已实现，缺少网络层

### 8.2 Phase 2: Networking (Week 3-4) ⏳

**目标**: 两个节点在局域网发现并通信

**任务**:
```
☐ 1. mDNS 发现服务 (core/hive/discovery/mdns.ts)
   • 使用 Bonjour (macOS 原生) 或 node-bonjour 库
   • 服务类型: _solar-hive._tcp
   • 广播: nodeId, tier, capabilities, status

☐ 2. 点对点通信 (core/hive/transport/p2p.ts)
   • TCP Socket 连接
   • JSON-RPC 2.0 消息格式
   • Heartbeat 机制 (30s 间隔)

☐ 3. Coordinator 选举 (core/hive/coordinator.ts)
   • 基于信誉+在线时长评分
   • Raft-like 选举流程
   • 主备切换

☐ 4. 基础测试
   • 2节点发现 < 5s
   • 消息往返 < 50ms
   • 选举收敛 < 10s
```

**验收标准**:
```bash
$ bun core/hive/cli/node.ts start --name="节点1"
[HIVE] ✓ 节点启动成功
[HIVE] ✓ 发现 1 个其他节点: 节点2 (10.0.1.5)
[HIVE] ✓ 选举 Coordinator: 节点2 (信誉 92)
```

### 8.3 Phase 3: Task Delegation (Week 5-6) ⏳

**目标**: 节点间任务委托

**任务**:
```
☐ 1. 任务市场 (core/hive/market/index.ts)
   • Publish 任务广播
   • Bid 竞标收集
   • Accept 接受通知
   • Escrow 积分托管

☐ 2. Handoff 协议 (core/hive/handoff.ts)
   • 类似 OpenAI Swarm
   • 任务上下文传递
   • 结果回传

☐ 3. 沙箱执行 (core/hive/sandbox.ts)
   • 资源限制 (内存/CPU/时间)
   • 文件访问控制
   • 网络策略

☐ 4. 集成测试
   • 节点A 发布任务
   • 节点B 竞标并执行
   • 节点A 验证结果
   • 积分结算
```

**验收标准**:
```bash
$ bun core/hive/cli/admin.ts publish \
  --task="审查 src/main.ts" \
  --agent="reviewer" \
  --reward=50

[Market] ✓ 任务已发布: task-abc
[Market] ✓ 收到 2 个竞标
[Market] ✓ 选择赢家: node-C (score 85.3)
[Market] ✓ 任务执行中...
[Market] ✓ 结果已验证
[Market] ✓ 积分已结算: node-C +50
```

### 8.4 Phase 4: Sync & Security (Week 7-8) ⏳

**目标**: 状态同步与安全加固

**任务**:
```
☐ 1. CRDT 同步 (core/hive/sync/crdt.ts)
   • LWW Register (节点列表)
   • Append-Only Log (积分账本)
   • G-Counter (统计计数)

☐ 2. mTLS 认证 (core/hive/security/auth.ts)
   • 自签名 CA 或 Let's Encrypt
   • 节点证书生成
   • 双向验证

☐ 3. 数据加密 (core/hive/security/encryption.ts)
   • AES-256-GCM 消息加密
   • 敏感数据识别与过滤
   • 密钥轮换 (90天)

☐ 4. 安全审计
   • 渗透测试
   • 权限验证
   • 日志审计
```

### 8.5 Phase 5: Fault Tolerance (Week 9-10) ⏳

**目标**: 容错与自愈

**任务**:
```
☐ 1. Heartbeat 监控 (core/hive/fault/heartbeat.ts)
   • 30s 间隔
   • 3次失败标记离线
   • 自动任务迁移

☐ 2. 任务重试 (core/hive/fault/retry.ts)
   • 指数退避 (1s → 2s → 4s → 8s)
   • 最多 3 次重试
   • 超时自动 Escalate

☐ 3. 结果验证 (core/hive/fault/verifier.ts)
   • Self / Deterministic / Peer / Consensus
   • 多数确认机制
   • 争议仲裁

☐ 4. Chaos 测试
   • 随机节点下线
   • 网络分区
   • 任务并发冲突
```

### 8.6 Phase 6: Production (Week 11-12) ⏳

**目标**: 生产就绪

**任务**:
```
☐ 1. CLI 工具
   • hive-node (节点管理)
   • hive-admin (网络管理)
   • hive-monitor (监控面板)

☐ 2. Dashboard UI
   • 网络拓扑可视化
   • 任务市场实时状态
   • 节点性能监控
   • 积分账本浏览

☐ 3. 文档
   • 用户手册
   • 部署指南
   • API 参考
   • 最佳实践

☐ 4. 性能调优
   • 消息压缩
   • 连接池
   • 缓存策略
```

---

## 9. PoC 原型

### 9.1 最小可行原型 (Week 1-2)

**目标**: 验证核心概念

**场景**: 2台 Mac mini 在同一局域网

**演示流程**:
```
1. 节点 A 启动:
   $ bun core/hive/cli/node.ts start --name="家庭主机"

2. 节点 B 启动:
   $ bun core/hive/cli/node.ts start --name="书房主机"

3. 自动发现:
   [Node-A] ✓ 发现节点: 家庭主机 (10.0.1.100)
   [Node-B] ✓ 发现节点: 书房主机 (10.0.1.101)

4. 选举 Coordinator:
   [Network] ✓ Coordinator 选举完成: 家庭主机 (信誉 100)

5. 发布任务 (在节点A):
   $ bun core/hive/cli/admin.ts publish \
     --task="@Reviewer 审查 main.ts" \
     --reward=50

6. 竞标 (节点B):
   [Node-B] ✓ 收到任务: task-001
   [Node-B] ✓ 能力匹配: Reviewer ✓, 负载 20%
   [Node-B] ✓ 发送竞标: 价格 40, 预估 2min

7. 执行 (节点B):
   [Node-B] ✓ 竞标胜出
   [Node-B] ✓ 执行任务...
   [Node-B] ✓ 完成: 发现 3 个问题

8. 验证 (节点A):
   [Node-A] ✓ 收到结果
   [Node-A] ✓ 验证通过 (Deterministic)

9. 结算:
   [Network] ✓ 积分转账: 节点A → 节点B (50 积分)
   [Network] ✓ 信誉更新: 节点B 信誉 100 → 102
```

### 9.2 成功指标

| 指标 | 目标值 | 测量方式 |
|------|--------|----------|
| 节点发现时间 | <5s | mDNS 响应时间 |
| 消息往返延迟 | <50ms | LAN ping + 协议开销 |
| 任务分配成功率 | >90% | 成功执行 / 总任务 |
| Coordinator 选举时间 | <10s | 从节点上线到选举完成 |
| 状态同步延迟 | <5s | CRDT 最终一致性 |
| 节点失败恢复时间 | <30s | Heartbeat 超时 + 任务迁移 |

---

## 10. 总结

### 10.1 创新点

| 创新 | 说明 | 对比 |
|------|------|------|
| **任务而非参数** | 只传任务描述和结果 | 联邦学习传梯度 (MB级) |
| **竞标机制** | 节点竞标任务 | Kubernetes 中心调度 |
| **积分经济** | 激励贡献而非Token | 区块链 Gas Fee |
| **异构友好** | 不同算力设备协同 | 联邦学习要求同构 |
| **边缘优先** | 本地优先网络次之云端兜底 | 传统云优先 |

### 10.2 潜在价值

**小区场景** (20户家庭):
- 算力聚合: 20 × 38TOPS = **760 TOPS** (等效 RTX 4090 × 3)
- 成本分摊: 每户 $10/月 API → 共同承担
- 隐私保护: 数据不出家庭网络
- 响应速度: LAN 延迟 <10ms

**vs 云端方案**:
- 云端 GPU 租用: $500+/月
- HIVE 小区网络: $0 硬件 + $200 API 分摊 = $10/户/月

**ROI**: 节省 96% 成本

---

## 11. 下一步行动

### 11.1 立即可做 (本周)

```
☐ 1. 完善 HIVE 协议 Schema
   • 补充网络层表定义
   • 添加同步机制表

☐ 2. 实现 mDNS 发现
   • 测试 Bonjour 库
   • 验证跨设备发现

☐ 3. 原型 CLI
   • hive-node start
   • hive-admin publish
   • hive-monitor
```

### 11.2 近期规划 (2-4周)

```
☐ 1. Phase 2 完整实现
☐ 2. 2-3 台设备测试
☐ 3. 性能基准测试
☐ 4. 文档完善
```

### 11.3 长期愿景 (3-6个月)

```
☐ 1. 小区试点 (5-10 户)
☐ 2. 移动端支持 (iPhone/iPad)
☐ 3. 跨小区联邦 (城市级网络)
☐ 4. 开源社区版本
```

---

## 附录 A: 继承人记忆存档

**记忆 ID**: `mem_heir_proposal_002`
**时间**: 2026-02-03 15:15:24
**命名空间**: `learning/heir`

```json
{
  "proposer": "李卓远 (继承人)",
  "lesson": "多个用户(如小区20户)的设备可以组成联邦网络，不传参数不传权重，只传任务，实现算力聚合",
  "protocol": "HIVE (Heterogeneous Intelligent Virtual Ecosystem)",
  "key_principles": [
    "不传参数(隐私)",
    "不传权重(太大)",
    "只传任务",
    "端到端加密",
    "积分激励"
  ],
  "potential": "20节点×38TOPS = 760TOPS，等效中型GPU服务器",
  "validated_at": "2026-02-03 15:15:24",
  "chinese_name": "蜂巢 / 社区智能蜂巢",
  "named_by": "李卓远 (继承人)"
}
```

---

## 附录 B: 参考文献

**分布式 AI**:
- [Federated Learning Framework 2026](https://www.mdpi.com/1424-8220/25/4/1266)
- [Edge AI Autonomous Systems](https://www.xenonstack.com/blog/edge-ai-autonomous-systems)
- [DMAS Decentralized Multi-Agent Swarms](https://www.arxiv.org/pdf/2601.17303)

**协作系统**:
- [Multi-Agent Collaboration Guide 2026](https://dev.to/eira-wexford/how-to-build-multi-agent-systems-complete-2026-guide-1io6)
- [Decentralized Task Allocation](https://www.nature.com/articles/s41598-025-21709-9)
- [OpenAI Swarm](https://github.com/openai/swarm)
- [CrewAI Hierarchical Delegation](https://activewizards.com/blog/hierarchical-ai-agents-a-guide-to-crewai-delegation)

**共识与激励**:
- [IMF Blockchain Consensus 2025](https://www.imf.org/-/media/files/publications/wp/2025/english/wpiea2025186-source-pdf.pdf)
- [Blockchain Incentive Mechanisms](https://dl.acm.org/doi/full/10.1145/3539604)

**边缘计算**:
- [OpenYurt CNCF Incubation](https://www.cncf.io/blog/2025/07/02/openyurt-becomes-a-cncf-incubating-project/)
- [KubeEdge GitHub](https://github.com/kubeedge/kubeedge)

**P2P 网络**:
- [IPFS Official](https://ipfs.tech/)
- [libp2p GossipSub](https://github.com/libp2p/specs/blob/master/pubsub/gossipsub/gossipsub-v1.1.md)

---

*设计基于继承人李卓远的构想*
*协议命名: HIVE (蜂巢)*
*Solar v2.0 分布式扩展*
