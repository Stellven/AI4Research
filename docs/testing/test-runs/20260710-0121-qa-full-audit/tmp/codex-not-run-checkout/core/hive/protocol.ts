/**
 * HIVE Protocol - Message Protocol
 * 消息创建、序列化、验证
 */

import { randomUUID } from 'crypto';
import type {
  HiveMessage,
  MessageType,
  TaskOfferPayload,
  BidPayload,
  AssignPayload,
  ResultPayload,
  VerifyPayload,
  CreditPayload,
  HeartbeatPayload,
  HiveTask,
  TaskResult,
  NodeCapability,
} from './types';

// ============================================================
// 消息工厂
// ============================================================

export class MessageFactory {
  constructor(private nodeId: string) {}

  private createMessage<T>(type: MessageType, payload: T, to?: string): HiveMessage<T> {
    return {
      messageId: randomUUID(),
      type,
      from: this.nodeId,
      to,
      payload,
      timestamp: new Date(),
    };
  }

  // TASK_OFFER - 广播任务
  taskOffer(task: HiveTask, biddingDeadlineMs: number = 5000): HiveMessage<TaskOfferPayload> {
    return this.createMessage('TASK_OFFER', {
      task,
      biddingDeadline: new Date(Date.now() + biddingDeadlineMs),
    });
  }

  // BID - 竞标任务
  bid(
    taskId: string,
    capabilities: NodeCapability[],
    estimatedLatencyMs: number,
    estimatedCredits: number,
    confidence: number
  ): HiveMessage<BidPayload> {
    return this.createMessage('BID', {
      taskId,
      nodeId: this.nodeId,
      capabilities,
      estimatedLatencyMs,
      estimatedCredits,
      confidence,
    });
  }

  // ASSIGN - 分配任务
  assign(taskId: string, assignedNodeId: string, credits: number): HiveMessage<AssignPayload> {
    return this.createMessage('ASSIGN', {
      taskId,
      assignedNodeId,
      credits,
    }, assignedNodeId);
  }

  // RESULT - 返回结果
  result(taskId: string, taskResult: TaskResult): HiveMessage<ResultPayload> {
    return this.createMessage('RESULT', {
      taskId,
      result: taskResult,
    });
  }

  // VERIFY - 验证结果
  verify(
    taskId: string,
    verified: boolean,
    creditsAwarded: number,
    feedback?: string
  ): HiveMessage<VerifyPayload> {
    return this.createMessage('VERIFY', {
      taskId,
      verified,
      creditsAwarded,
      feedback,
    });
  }

  // CREDIT - 积分转账
  credit(to: string, amount: number, reason: string, taskId?: string): HiveMessage<CreditPayload> {
    return this.createMessage('CREDIT', {
      from: this.nodeId,
      to,
      amount,
      reason,
      taskId,
    }, to);
  }

  // HEARTBEAT - 心跳
  heartbeat(status: 'online' | 'offline' | 'busy', currentTasks: number, credits: number): HiveMessage<HeartbeatPayload> {
    return this.createMessage('HEARTBEAT', {
      nodeId: this.nodeId,
      status,
      currentTasks,
      credits,
    });
  }

  // JOIN - 加入网络
  join(nodeInfo: { name: string; capabilities: NodeCapability[] }): HiveMessage<typeof nodeInfo> {
    return this.createMessage('JOIN', nodeInfo);
  }

  // LEAVE - 离开网络
  leave(reason?: string): HiveMessage<{ reason?: string }> {
    return this.createMessage('LEAVE', { reason });
  }
}

// ============================================================
// 消息序列化
// ============================================================

export function serializeMessage(message: HiveMessage): string {
  return JSON.stringify(message, (key, value) => {
    if (value instanceof Date) {
      return { __type: 'Date', value: value.toISOString() };
    }
    return value;
  });
}

export function deserializeMessage<T = unknown>(data: string): HiveMessage<T> {
  return JSON.parse(data, (key, value) => {
    if (value && typeof value === 'object' && value.__type === 'Date') {
      return new Date(value.value);
    }
    return value;
  });
}

// ============================================================
// 消息验证
// ============================================================

export function validateMessage(message: HiveMessage): { valid: boolean; error?: string } {
  // 基础验证
  if (!message.messageId) {
    return { valid: false, error: 'Missing messageId' };
  }
  if (!message.type) {
    return { valid: false, error: 'Missing type' };
  }
  if (!message.from) {
    return { valid: false, error: 'Missing from' };
  }
  if (!message.timestamp) {
    return { valid: false, error: 'Missing timestamp' };
  }

  // 类型特定验证
  switch (message.type) {
    case 'TASK_OFFER': {
      const payload = message.payload as TaskOfferPayload;
      if (!payload.task || !payload.task.taskId) {
        return { valid: false, error: 'Invalid TASK_OFFER payload' };
      }
      break;
    }
    case 'BID': {
      const payload = message.payload as BidPayload;
      if (!payload.taskId || !payload.nodeId) {
        return { valid: false, error: 'Invalid BID payload' };
      }
      if (payload.confidence < 0 || payload.confidence > 1) {
        return { valid: false, error: 'BID confidence must be 0-1' };
      }
      break;
    }
    case 'ASSIGN': {
      const payload = message.payload as AssignPayload;
      if (!payload.taskId || !payload.assignedNodeId) {
        return { valid: false, error: 'Invalid ASSIGN payload' };
      }
      break;
    }
    case 'RESULT': {
      const payload = message.payload as ResultPayload;
      if (!payload.taskId || payload.result === undefined) {
        return { valid: false, error: 'Invalid RESULT payload' };
      }
      break;
    }
    case 'VERIFY': {
      const payload = message.payload as VerifyPayload;
      if (!payload.taskId || payload.verified === undefined) {
        return { valid: false, error: 'Invalid VERIFY payload' };
      }
      break;
    }
    case 'CREDIT': {
      const payload = message.payload as CreditPayload;
      if (!payload.from || !payload.to || payload.amount === undefined) {
        return { valid: false, error: 'Invalid CREDIT payload' };
      }
      if (payload.amount < 0) {
        return { valid: false, error: 'CREDIT amount cannot be negative' };
      }
      break;
    }
  }

  return { valid: true };
}

// ============================================================
// 任务创建辅助
// ============================================================

export function createTask(params: {
  title: string;
  description: string;
  requiredAgents: string[];
  minTier?: 'edge' | 'local' | 'cloud';
  priority?: 'low' | 'normal' | 'high' | 'urgent';
  deadline?: Date;
}): HiveTask {
  return {
    taskId: randomUUID(),
    title: params.title,
    description: params.description,
    requirements: {
      requiredAgents: params.requiredAgents,
      minTier: params.minTier || 'edge',
    },
    priority: params.priority || 'normal',
    status: 'pending',
    createdBy: '', // 由发送时填充
    createdAt: new Date(),
    deadline: params.deadline,
  };
}
