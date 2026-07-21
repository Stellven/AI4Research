/**
 * HIVE Protocol - Core Types
 * Heterogeneous Intelligent Virtual Ecosystem
 *
 * 核心原则：不传参数、不传权重、只传任务
 * 命名者：李卓远 (继承人)
 */

// ============================================================
// 节点类型
// ============================================================

export type NodeTier = 'edge' | 'local' | 'cloud';

export interface NodeCapability {
  agentId: string;           // Agent ID
  agentName: string;         // 如 "Coder", "Researcher"
  tier: NodeTier;            // 运行层级
  maxConcurrent: number;     // 最大并发任务数
  avgLatencyMs: number;      // 平均延迟
  successRate: number;       // 成功率 0-1
  creditsPerTask: number;    // 每任务消耗积分
}

export interface HiveNode {
  nodeId: string;            // 唯一标识 (UUID)
  name: string;              // 节点名称
  owner: string;             // 所有者
  tier: NodeTier;            // 节点层级
  capabilities: NodeCapability[];  // 能力列表
  status: 'online' | 'offline' | 'busy';
  credits: number;           // 当前积分
  joinedAt: Date;
  lastHeartbeat: Date;
}

// ============================================================
// 任务类型
// ============================================================

export type TaskPriority = 'low' | 'normal' | 'high' | 'urgent';
export type TaskStatus = 'pending' | 'bidding' | 'assigned' | 'running' | 'completed' | 'failed' | 'verified';

export interface TaskRequirement {
  requiredAgents: string[];  // 需要的 Agent 类型
  minTier: NodeTier;         // 最低层级要求
  maxLatencyMs?: number;     // 最大可接受延迟
  minSuccessRate?: number;   // 最低成功率要求
}

export interface HiveTask {
  taskId: string;            // 唯一标识
  title: string;             // 任务标题
  description: string;       // 任务描述 (自然语言)
  requirements: TaskRequirement;
  priority: TaskPriority;
  status: TaskStatus;

  // 不传参数、不传权重，只传任务描述
  // 执行节点自行理解并执行

  createdBy: string;         // 发起节点
  assignedTo?: string;       // 执行节点
  result?: TaskResult;

  createdAt: Date;
  deadline?: Date;
  completedAt?: Date;
}

export interface TaskResult {
  success: boolean;
  output: string;            // 结果描述
  artifacts?: string[];      // 产出物路径
  metrics?: {
    tokensUsed: number;
    latencyMs: number;
    cost: number;
  };
  error?: string;
}

// ============================================================
// 协议消息类型
// ============================================================

export type MessageType =
  | 'TASK_OFFER'    // 任务广播
  | 'BID'           // 能力竞标
  | 'ASSIGN'        // 任务分配
  | 'RESULT'        // 结果返回
  | 'VERIFY'        // 结果验证
  | 'CREDIT'        // 积分结算
  | 'HEARTBEAT'     // 心跳
  | 'JOIN'          // 加入网络
  | 'LEAVE';        // 离开网络

export interface HiveMessage<T = unknown> {
  messageId: string;
  type: MessageType;
  from: string;              // 发送节点 ID
  to?: string;               // 目标节点 ID (广播时为空)
  payload: T;
  timestamp: Date;
  signature?: string;        // 签名 (可选)
}

// ============================================================
// 具体消息负载类型
// ============================================================

export interface TaskOfferPayload {
  task: HiveTask;
  biddingDeadline: Date;     // 竞标截止时间
}

export interface BidPayload {
  taskId: string;
  nodeId: string;
  capabilities: NodeCapability[];
  estimatedLatencyMs: number;
  estimatedCredits: number;
  confidence: number;        // 置信度 0-1
}

export interface AssignPayload {
  taskId: string;
  assignedNodeId: string;
  credits: number;           // 预付积分
}

export interface ResultPayload {
  taskId: string;
  result: TaskResult;
}

export interface VerifyPayload {
  taskId: string;
  verified: boolean;
  feedback?: string;
  creditsAwarded: number;
}

export interface CreditPayload {
  from: string;
  to: string;
  amount: number;
  reason: string;
  taskId?: string;
}

export interface HeartbeatPayload {
  nodeId: string;
  status: HiveNode['status'];
  currentTasks: number;
  credits: number;
}

// ============================================================
// 积分系统
// ============================================================

export interface CreditTransaction {
  txId: string;
  from: string;
  to: string;
  amount: number;
  type: 'task_payment' | 'task_reward' | 'penalty' | 'bonus';
  taskId?: string;
  timestamp: Date;
}

export interface CreditAccount {
  nodeId: string;
  balance: number;
  earned: number;
  spent: number;
  transactions: CreditTransaction[];
}

// ============================================================
// 网络配置
// ============================================================

export interface HiveConfig {
  networkId: string;         // 网络标识 (如 "community-001")
  name: string;              // 网络名称
  maxNodes: number;          // 最大节点数
  biddingTimeoutMs: number;  // 竞标超时
  heartbeatIntervalMs: number;
  creditSettings: {
    initialCredits: number;  // 新节点初始积分
    taskBaseReward: number;  // 任务基础奖励
    penaltyRate: number;     // 失败惩罚率
  };
}

// ============================================================
// 默认配置
// ============================================================

export const DEFAULT_HIVE_CONFIG: HiveConfig = {
  networkId: 'solar-hive-001',
  name: 'Solar Community Hive',
  maxNodes: 50,
  biddingTimeoutMs: 5000,
  heartbeatIntervalMs: 30000,
  creditSettings: {
    initialCredits: 100,
    taskBaseReward: 10,
    penaltyRate: 0.1,
  },
};
