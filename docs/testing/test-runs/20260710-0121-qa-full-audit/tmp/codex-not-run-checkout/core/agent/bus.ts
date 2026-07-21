/**
 * Agent Communication Bus
 *
 * Central message routing and delivery system for Solar agents
 */

import type {
  AgentMessage,
  AgentId,
  MessageType,
  Priority,
} from "./protocol";
import { validateMessage } from "./protocol";

// ==================== Types ====================

export type MessageHandler = (message: AgentMessage) => void | Promise<void>;

export type MessageFilter = (message: AgentMessage) => boolean;

export interface Subscription {
  id: string;
  agentId: AgentId;
  types?: MessageType[];
  filter?: MessageFilter;
  handler: MessageHandler;
}

export interface BusConfig {
  maxQueueSize?: number;
  processingInterval?: number;
  enableLogging?: boolean;
  onError?: (error: Error, message: AgentMessage) => void;
}

export interface BusStats {
  messagesReceived: number;
  messagesDelivered: number;
  messagesFailed: number;
  queueSize: number;
  activeSubscriptions: number;
}

// ==================== Priority Queue ====================

class PriorityQueue<T> {
  private items: Array<{ item: T; priority: number }> = [];

  enqueue(item: T, priority: number): void {
    this.items.push({ item, priority });
    this.items.sort((a, b) => b.priority - a.priority); // Higher priority first
  }

  dequeue(): T | undefined {
    return this.items.shift()?.item;
  }

  peek(): T | undefined {
    return this.items[0]?.item;
  }

  size(): number {
    return this.items.length;
  }

  isEmpty(): boolean {
    return this.items.length === 0;
  }

  clear(): void {
    this.items = [];
  }
}

const PRIORITY_VALUES: Record<Priority, number> = {
  critical: 4,
  high: 3,
  normal: 2,
  low: 1,
};

// ==================== Agent Bus ====================

export class AgentBus {
  private subscriptions: Map<string, Subscription> = new Map();
  private agentSubscriptions: Map<AgentId, Set<string>> = new Map();
  private messageQueue: PriorityQueue<AgentMessage>;
  private processing = false;
  private processingTimer?: NodeJS.Timer;
  private config: Required<BusConfig>;
  private stats: BusStats = {
    messagesReceived: 0,
    messagesDelivered: 0,
    messagesFailed: 0,
    queueSize: 0,
    activeSubscriptions: 0,
  };

  // Message history for correlation
  private messageHistory: Map<string, AgentMessage> = new Map();
  private maxHistorySize = 1000;

  constructor(config: BusConfig = {}) {
    this.config = {
      maxQueueSize: config.maxQueueSize ?? 10000,
      processingInterval: config.processingInterval ?? 10,
      enableLogging: config.enableLogging ?? false,
      onError: config.onError ?? (() => {}),
    };
    this.messageQueue = new PriorityQueue();
  }

  // ==================== Lifecycle ====================

  start(): void {
    if (this.processing) return;
    this.processing = true;

    this.processingTimer = setInterval(() => {
      this.processQueue();
    }, this.config.processingInterval);

    this.log("Bus started");
  }

  stop(): void {
    if (!this.processing) return;
    this.processing = false;

    if (this.processingTimer) {
      clearInterval(this.processingTimer);
    }

    this.log("Bus stopped");
  }

  // ==================== Subscription ====================

  subscribe(
    agentId: AgentId,
    handler: MessageHandler,
    options?: {
      types?: MessageType[];
      filter?: MessageFilter;
    }
  ): string {
    const subscriptionId = `sub_${agentId}_${Date.now()}`;

    const subscription: Subscription = {
      id: subscriptionId,
      agentId,
      types: options?.types,
      filter: options?.filter,
      handler,
    };

    this.subscriptions.set(subscriptionId, subscription);

    // Track by agent
    if (!this.agentSubscriptions.has(agentId)) {
      this.agentSubscriptions.set(agentId, new Set());
    }
    this.agentSubscriptions.get(agentId)!.add(subscriptionId);

    this.stats.activeSubscriptions = this.subscriptions.size;
    this.log(`Agent ${agentId} subscribed: ${subscriptionId}`);

    return subscriptionId;
  }

  unsubscribe(subscriptionId: string): boolean {
    const subscription = this.subscriptions.get(subscriptionId);
    if (!subscription) return false;

    this.subscriptions.delete(subscriptionId);
    this.agentSubscriptions.get(subscription.agentId)?.delete(subscriptionId);

    this.stats.activeSubscriptions = this.subscriptions.size;
    this.log(`Unsubscribed: ${subscriptionId}`);

    return true;
  }

  unsubscribeAll(agentId: AgentId): void {
    const subIds = this.agentSubscriptions.get(agentId);
    if (subIds) {
      for (const id of subIds) {
        this.subscriptions.delete(id);
      }
      this.agentSubscriptions.delete(agentId);
    }
    this.stats.activeSubscriptions = this.subscriptions.size;
    this.log(`Agent ${agentId} unsubscribed all`);
  }

  // ==================== Publishing ====================

  publish(message: AgentMessage): boolean {
    // Validate message
    const validation = validateMessage(message);
    if (!validation.valid) {
      this.log(`Invalid message: ${validation.errors.join(", ")}`);
      return false;
    }

    // Check queue capacity
    if (this.messageQueue.size() >= this.config.maxQueueSize) {
      this.log("Queue full, dropping message");
      this.stats.messagesFailed++;
      return false;
    }

    // Enqueue with priority
    const priority = PRIORITY_VALUES[message.priority];
    this.messageQueue.enqueue(message, priority);
    this.stats.messagesReceived++;
    this.stats.queueSize = this.messageQueue.size();

    // Store in history
    this.storeInHistory(message);

    this.log(`Message queued: ${message.id} (${message.type}) ${message.from} → ${message.to}`);

    return true;
  }

  // Convenience method for request-response pattern
  async request(
    message: AgentMessage,
    timeout = 30000
  ): Promise<AgentMessage | null> {
    return new Promise((resolve) => {
      const timeoutId = setTimeout(() => {
        this.unsubscribe(subId);
        resolve(null);
      }, timeout);

      // Subscribe for response
      const subId = this.subscribe(
        message.from,
        (response) => {
          if (response.correlationId === message.id) {
            clearTimeout(timeoutId);
            this.unsubscribe(subId);
            resolve(response);
          }
        },
        {
          types: ["result", "error", "response"],
          filter: (msg) => msg.correlationId === message.id,
        }
      );

      // Send the message
      this.publish(message);
    });
  }

  // ==================== Queue Processing ====================

  private async processQueue(): Promise<void> {
    if (this.messageQueue.isEmpty()) return;

    const message = this.messageQueue.dequeue();
    if (!message) return;

    this.stats.queueSize = this.messageQueue.size();

    try {
      await this.deliverMessage(message);
      this.stats.messagesDelivered++;
    } catch (error) {
      this.stats.messagesFailed++;
      this.config.onError(error as Error, message);
      this.log(`Delivery failed: ${message.id} - ${error}`);

      // Retry logic
      if ((message.retryCount ?? 0) < 3) {
        message.retryCount = (message.retryCount ?? 0) + 1;
        this.messageQueue.enqueue(message, PRIORITY_VALUES[message.priority] - 1);
        this.log(`Retrying message: ${message.id} (attempt ${message.retryCount})`);
      }
    }
  }

  private async deliverMessage(message: AgentMessage): Promise<void> {
    const recipients = this.getRecipients(message);

    for (const subscription of recipients) {
      // Apply type filter
      if (subscription.types && !subscription.types.includes(message.type)) {
        continue;
      }

      // Apply custom filter
      if (subscription.filter && !subscription.filter(message)) {
        continue;
      }

      // Deliver
      try {
        await subscription.handler(message);
        this.log(`Delivered to ${subscription.agentId}: ${message.id}`);
      } catch (error) {
        this.log(`Handler error for ${subscription.agentId}: ${error}`);
        throw error;
      }
    }
  }

  private getRecipients(message: AgentMessage): Subscription[] {
    const recipients: Subscription[] = [];

    if (message.to === "broadcast") {
      // Broadcast to all except sender
      for (const sub of this.subscriptions.values()) {
        if (sub.agentId !== message.from) {
          recipients.push(sub);
        }
      }
    } else if (Array.isArray(message.to)) {
      // Multiple recipients
      for (const agentId of message.to) {
        const subs = this.agentSubscriptions.get(agentId);
        if (subs) {
          for (const subId of subs) {
            const sub = this.subscriptions.get(subId);
            if (sub) recipients.push(sub);
          }
        }
      }
    } else {
      // Single recipient
      const subs = this.agentSubscriptions.get(message.to);
      if (subs) {
        for (const subId of subs) {
          const sub = this.subscriptions.get(subId);
          if (sub) recipients.push(sub);
        }
      }
    }

    return recipients;
  }

  // ==================== History ====================

  private storeInHistory(message: AgentMessage): void {
    this.messageHistory.set(message.id, message);

    // Cleanup old messages
    if (this.messageHistory.size > this.maxHistorySize) {
      const toDelete = this.messageHistory.size - this.maxHistorySize;
      const keys = Array.from(this.messageHistory.keys()).slice(0, toDelete);
      for (const key of keys) {
        this.messageHistory.delete(key);
      }
    }
  }

  getMessage(messageId: string): AgentMessage | undefined {
    return this.messageHistory.get(messageId);
  }

  getCorrelatedMessages(correlationId: string): AgentMessage[] {
    const messages: AgentMessage[] = [];
    for (const msg of this.messageHistory.values()) {
      if (msg.correlationId === correlationId || msg.id === correlationId) {
        messages.push(msg);
      }
    }
    return messages.sort((a, b) => a.timestamp - b.timestamp);
  }

  // ==================== Stats ====================

  getStats(): BusStats {
    return { ...this.stats };
  }

  // ==================== Logging ====================

  private log(message: string): void {
    if (this.config.enableLogging) {
      console.log(`[AgentBus] ${message}`);
    }
  }
}

// ==================== Singleton ====================

let busInstance: AgentBus | null = null;

export function getBus(config?: BusConfig): AgentBus {
  if (!busInstance) {
    busInstance = new AgentBus(config);
    busInstance.start();
  }
  return busInstance;
}

export function resetBus(): void {
  if (busInstance) {
    busInstance.stop();
    busInstance = null;
  }
}
