/**
 * HIVE P2P Transport
 * TCP Socket 节点间通信
 */

import net from 'net';
import { randomUUID } from 'crypto';
import type { HiveMessage, MessageType } from '../types';

const HEARTBEAT_INTERVAL = 30000; // 30s

export interface P2PConfig {
  port: number;
  nodeId: string;
  onMessage?: (msg: HiveMessage, from: string) => void;
  onPeerConnected?: (peerId: string, address: string) => void;
  onPeerDisconnected?: (peerId: string) => void;
}

interface Peer {
  id: string;
  socket: net.Socket;
  address: string;
  lastSeen: Date;
}

export class P2PTransport {
  private server?: net.Server;
  private peers = new Map<string, Peer>();
  private config: P2PConfig;
  private heartbeatTimer?: NodeJS.Timeout;
  private buffer = new Map<string, string>(); // 未完成消息缓冲

  constructor(config: P2PConfig) {
    this.config = config;
  }

  /**
   * 启动 TCP 服务器
   */
  async listen(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.server = net.createServer((socket) => {
        this.handleIncomingConnection(socket);
      });

      this.server.on('error', (err) => {
        console.error('[P2P] 服务器错误:', err.message);
        reject(err);
      });

      this.server.listen(this.config.port, () => {
        console.log(`[P2P] ✓ 监听端口: ${this.config.port}`);
        this.startHeartbeat();
        resolve();
      });
    });
  }

  /**
   * 连接到其他节点
   */
  async connect(nodeId: string, host: string, port: number): Promise<void> {
    // 避免重复连接
    if (this.peers.has(nodeId)) {
      console.log(`[P2P] 节点已连接: ${nodeId}`);
      return;
    }

    return new Promise((resolve, reject) => {
      const socket = net.connect({ host, port }, () => {
        console.log(`[P2P] ✓ 已连接: ${host}:${port}`);

        // 发送握手消息
        this.sendHandshake(socket, nodeId);

        this.peers.set(nodeId, {
          id: nodeId,
          socket,
          address: `${host}:${port}`,
          lastSeen: new Date(),
        });

        this.config.onPeerConnected?.(nodeId, `${host}:${port}`);
        resolve();
      });

      socket.on('data', (data) => {
        this.handleData(nodeId, data);
      });

      socket.on('error', (err) => {
        console.error(`[P2P] 连接错误 (${nodeId}):`, err.message);
        this.removePeer(nodeId);
        reject(err);
      });

      socket.on('close', () => {
        console.log(`[P2P] 连接关闭: ${nodeId}`);
        this.removePeer(nodeId);
      });
    });
  }

  /**
   * 发送消息
   */
  send<T = unknown>(to: string, type: MessageType, payload: T): boolean {
    const peer = this.peers.get(to);
    if (!peer) {
      console.error(`[P2P] 节点未连接: ${to}`);
      return false;
    }

    const message: HiveMessage<T> = {
      messageId: randomUUID(),
      type,
      from: this.config.nodeId,
      to,
      payload,
      timestamp: new Date(),
    };

    try {
      const json = JSON.stringify(message);
      peer.socket.write(json + '\n'); // 使用换行符分隔消息
      return true;
    } catch (err) {
      console.error(`[P2P] 发送失败 (${to}):`, err);
      return false;
    }
  }

  /**
   * 广播消息给所有节点
   */
  broadcast<T = unknown>(type: MessageType, payload: T): number {
    let sent = 0;
    for (const [peerId] of this.peers) {
      if (this.send(peerId, type, payload)) {
        sent++;
      }
    }
    return sent;
  }

  /**
   * 获取已连接节点列表
   */
  getPeers(): Array<{ id: string; address: string; lastSeen: Date }> {
    return Array.from(this.peers.values()).map(p => ({
      id: p.id,
      address: p.address,
      lastSeen: p.lastSeen,
    }));
  }

  /**
   * 关闭服务
   */
  shutdown(): void {
    console.log('[P2P] 关闭服务...');

    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
    }

    // 关闭所有连接
    for (const peer of this.peers.values()) {
      peer.socket.destroy();
    }
    this.peers.clear();

    // 关闭服务器
    if (this.server) {
      this.server.close();
    }
  }

  // ============================================================
  // 私有方法
  // ============================================================

  /**
   * 处理入站连接
   */
  private handleIncomingConnection(socket: net.Socket): void {
    const address = `${socket.remoteAddress}:${socket.remotePort}`;
    console.log(`[P2P] 新连接: ${address}`);

    let peerId = `pending-${randomUUID()}`;

    socket.on('data', (data) => {
      // 第一条消息应该是 HANDSHAKE
      const msg = this.parseMessage(data.toString());
      if (msg && msg.type === 'JOIN') {
        peerId = msg.from;
        this.peers.set(peerId, {
          id: peerId,
          socket,
          address,
          lastSeen: new Date(),
        });
        console.log(`[P2P] ✓ 节点加入: ${peerId} (${address})`);
        this.config.onPeerConnected?.(peerId, address);
      }

      this.handleData(peerId, data);
    });

    socket.on('error', (err) => {
      console.error(`[P2P] Socket 错误 (${peerId}):`, err.message);
    });

    socket.on('close', () => {
      console.log(`[P2P] 节点断开: ${peerId}`);
      this.removePeer(peerId);
    });
  }

  /**
   * 处理接收到的数据
   */
  private handleData(peerId: string, data: Buffer): void {
    const peer = this.peers.get(peerId);
    if (!peer) return;

    // 更新最后活跃时间
    peer.lastSeen = new Date();

    // 处理分包的 JSON (按行分隔)
    const text = data.toString();
    const buffered = (this.buffer.get(peerId) || '') + text;
    const lines = buffered.split('\n');

    // 保留未完成的行
    this.buffer.set(peerId, lines.pop() || '');

    // 解析完整的消息
    for (const line of lines) {
      if (line.trim()) {
        const msg = this.parseMessage(line);
        if (msg) {
          this.handleMessage(msg, peerId);
        }
      }
    }
  }

  /**
   * 解析 JSON 消息
   */
  private parseMessage(text: string): HiveMessage | null {
    try {
      const msg = JSON.parse(text);
      msg.timestamp = new Date(msg.timestamp); // 恢复 Date 对象
      return msg;
    } catch (err) {
      console.error('[P2P] 消息解析失败:', text.substring(0, 100));
      return null;
    }
  }

  /**
   * 处理消息
   */
  private handleMessage(msg: HiveMessage, from: string): void {
    // 忽略自己发的消息
    if (msg.from === this.config.nodeId) {
      return;
    }

    // 更新节点活跃时间
    const peer = this.peers.get(from);
    if (peer) {
      peer.lastSeen = new Date();
    }

    // 回调处理
    this.config.onMessage?.(msg, from);
  }

  /**
   * 发送握手消息
   */
  private sendHandshake(socket: net.Socket, targetId: string): void {
    const message: HiveMessage = {
      messageId: randomUUID(),
      type: 'JOIN',
      from: this.config.nodeId,
      to: targetId,
      payload: { nodeId: this.config.nodeId },
      timestamp: new Date(),
    };

    socket.write(JSON.stringify(message) + '\n');
  }

  /**
   * 移除节点
   */
  private removePeer(peerId: string): void {
    this.peers.delete(peerId);
    this.buffer.delete(peerId);
    this.config.onPeerDisconnected?.(peerId);
  }

  /**
   * 启动心跳
   */
  private startHeartbeat(): void {
    this.heartbeatTimer = setInterval(() => {
      const now = Date.now();
      const timeout = 60000; // 60s 超时

      // 检查超时节点
      for (const [peerId, peer] of this.peers) {
        if (now - peer.lastSeen.getTime() > timeout) {
          console.log(`[P2P] 节点超时: ${peerId}`);
          this.removePeer(peerId);
        }
      }

      // 发送心跳
      this.broadcast('HEARTBEAT', {
        nodeId: this.config.nodeId,
        timestamp: new Date(),
      });
    }, HEARTBEAT_INTERVAL);
  }
}
