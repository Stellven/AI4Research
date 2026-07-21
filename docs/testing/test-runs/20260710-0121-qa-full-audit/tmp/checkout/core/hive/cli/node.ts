#!/usr/bin/env bun
/**
 * HIVE Node CLI
 * 节点启动和管理命令行工具
 */

import { randomUUID } from 'crypto';
import os from 'os';
import { MDNSDiscovery, type DiscoveredPeer } from '../discovery/mdns';
import { P2PTransport } from '../transport/p2p';
import { CoordinatorElection, FailoverManager } from '../coordinator';
import { NodeRegistry, createNodeCapabilities } from '../node';
import type { HiveNode, NodeTier, HiveMessage } from '../types';

const DEFAULT_PORT = 9876;
const DEFAULT_TIER: NodeTier = 'local';

interface NodeConfig {
  name?: string;
  tier?: NodeTier;
  port?: number;
  agents?: string[];
}

class HiveNodeCLI {
  private mdns?: MDNSDiscovery;
  private p2p?: P2PTransport;
  private registry: NodeRegistry;
  private election: CoordinatorElection;
  private failover: FailoverManager;
  private localNode?: HiveNode;
  private isRunning = false;

  constructor() {
    this.registry = new NodeRegistry();
    this.election = new CoordinatorElection();
    this.failover = new FailoverManager(this.election);
  }

  /**
   * 启动节点
   */
  async start(config: NodeConfig): Promise<void> {
    console.log('\n┌─ ☀️ HIVE Node ──────────────────────────────────────┐');
    console.log('│ Solar Community Neural Network                    │');
    console.log('└───────────────────────────────────────────────────┘\n');

    const nodeName = config.name || `Solar-${os.hostname()}`;
    const tier = config.tier || DEFAULT_TIER;
    const port = config.port || DEFAULT_PORT;

    // 默认能力: 根据 tier 自动选择
    const defaultAgents = this.getDefaultAgents(tier);
    const agents = config.agents || defaultAgents;

    // 注册本地节点
    this.localNode = this.registry.register({
      name: nodeName,
      owner: os.userInfo().username,
      tier,
      capabilities: createNodeCapabilities(agents),
    });

    console.log(`[HIVE] ✓ 节点启动成功: ${this.localNode.nodeId}`);
    console.log(`[HIVE]   名称: ${nodeName}`);
    console.log(`[HIVE]   层级: ${tier}`);
    console.log(`[HIVE]   能力: ${agents.join(', ')}`);
    console.log('');

    // 启动 P2P 服务
    this.p2p = new P2PTransport({
      port,
      nodeId: this.localNode.nodeId,
      onMessage: this.handleMessage.bind(this),
      onPeerConnected: this.handlePeerConnected.bind(this),
      onPeerDisconnected: this.handlePeerDisconnected.bind(this),
    });

    await this.p2p.listen();

    // 启动 mDNS 发现
    this.mdns = new MDNSDiscovery();
    this.mdns.advertise(this.localNode, port);
    this.mdns.startBrowsing({
      onPeerDiscovered: this.handlePeerDiscovered.bind(this),
      onPeerLost: this.handlePeerLost.bind(this),
    });

    this.isRunning = true;

    // 启动选举定时器 (5秒后第一次选举)
    setTimeout(() => {
      this.performElection();
    }, 5000);

    // 定期重新选举检查 (每 30 秒)
    setInterval(() => {
      this.checkReelection();
    }, 30000);

    console.log('[HIVE] ✓ 节点运行中... (Ctrl+C 退出)\n');

    // 优雅退出
    this.setupSignalHandlers();
  }

  /**
   * 查看节点状态
   */
  status(): void {
    console.log('\n┌─ 📊 Node Status ────────────────────────────────────┐');

    if (this.localNode) {
      console.log(`│ Node ID    ${this.localNode.nodeId.substring(0, 8)}...`);
      console.log(`│ Name       ${this.localNode.name}`);
      console.log(`│ Tier       ${this.localNode.tier}`);
      console.log(`│ Status     ${this.localNode.status}`);
      console.log(`│ Credits    ${this.localNode.credits}`);
    } else {
      console.log('│ 节点未启动');
    }

    console.log('├─────────────────────────────────────────────────────┤');

    const coordinator = this.failover.getCoordinator();
    if (coordinator) {
      console.log(`│ Coordinator  ${coordinator.coordinatorName} (${coordinator.score.toFixed(1)})`);
    } else {
      console.log('│ Coordinator  (未选举)');
    }

    console.log('└─────────────────────────────────────────────────────┘\n');
  }

  /**
   * 列出已发现的节点
   */
  peers(): void {
    const peers = this.mdns?.getPeers() || [];
    const connected = this.p2p?.getPeers() || [];

    console.log('\n┌─ 🌐 Discovered Peers ──────────────────────────────┐');
    console.log(`│ 已发现: ${peers.length} 个节点`);
    console.log('├─────────────────────────────────────────────────────┤');

    if (peers.length === 0) {
      console.log('│ (暂无发现的节点)');
    } else {
      for (const peer of peers) {
        const isConnected = connected.some(c => c.id === peer.nodeId);
        const status = isConnected ? '✓' : '○';
        console.log(`│ ${status} ${peer.name.padEnd(20)} ${peer.host}:${peer.port}`);
        console.log(`│   Tier: ${peer.tier} | Agents: ${peer.capabilities.slice(0, 3).join(', ')}`);
      }
    }

    console.log('└─────────────────────────────────────────────────────┘\n');
  }

  // ============================================================
  // 事件处理
  // ============================================================

  /**
   * 处理发现新节点
   */
  private async handlePeerDiscovered(peer: DiscoveredPeer): Promise<void> {
    console.log(`[HIVE] ✓ 发现节点: ${peer.name} (${peer.host}:${peer.port})`);

    // 注册到 Registry
    const node = this.registry.register({
      name: peer.name,
      owner: 'unknown',
      tier: peer.tier as NodeTier,
      capabilities: createNodeCapabilities(peer.capabilities),
    });

    // 连接 P2P
    try {
      await this.p2p?.connect(peer.nodeId, peer.host, peer.port);
    } catch (err) {
      console.error(`[HIVE] 连接失败: ${peer.name}`, err);
    }

    // 触发选举检查
    setTimeout(() => {
      this.performElection();
    }, 2000);
  }

  /**
   * 处理节点离线
   */
  private handlePeerLost(nodeId: string): void {
    console.log(`[HIVE] ✗ 节点离线: ${nodeId}`);
    this.registry.unregister(nodeId);

    // 检查是否是 Coordinator
    const coordinator = this.failover.getCoordinator();
    if (coordinator && coordinator.coordinatorId === nodeId) {
      this.handleCoordinatorFailure();
    }
  }

  /**
   * 处理 P2P 连接建立
   */
  private handlePeerConnected(peerId: string, address: string): void {
    console.log(`[P2P] ✓ 已连接: ${peerId} (${address})`);
  }

  /**
   * 处理 P2P 连接断开
   */
  private handlePeerDisconnected(peerId: string): void {
    console.log(`[P2P] ✗ 断开连接: ${peerId}`);

    // 检查是否是 Coordinator
    const coordinator = this.failover.getCoordinator();
    if (coordinator && coordinator.coordinatorId === peerId) {
      this.handleCoordinatorFailure();
    }
  }

  /**
   * 处理接收到的消息
   */
  private handleMessage(msg: HiveMessage, from: string): void {
    // 更新心跳
    if (msg.type === 'HEARTBEAT') {
      this.registry.heartbeat(from, 'online');
    }

    // 其他消息类型后续实现
  }

  /**
   * 执行选举
   */
  private performElection(): void {
    const nodes = this.registry.getOnlineNodes();
    if (nodes.length === 0) return;

    const result = this.election.elect(nodes);
    this.failover.setLeadership(result);

    // 显示选举结果
    const isMe = this.localNode && result.coordinatorId === this.localNode.nodeId;
    if (isMe) {
      console.log(`\n[HIVE] 🎯 当选 Coordinator (评分: ${result.score.toFixed(1)})\n`);
    } else {
      console.log(`\n[HIVE] ✓ Coordinator 选举: ${result.coordinatorName} (评分: ${result.score.toFixed(1)})\n`);
    }
  }

  /**
   * 检查是否需要重新选举
   */
  private checkReelection(): void {
    const coordinator = this.failover.getCoordinator();
    if (!coordinator) return;

    const nodes = this.registry.getOnlineNodes();
    if (this.election.shouldReelect(coordinator.coordinatorId, nodes)) {
      console.log('[HIVE] 触发重新选举...');
      this.performElection();
    }
  }

  /**
   * 处理 Coordinator 失效
   */
  private handleCoordinatorFailure(): void {
    console.log('[HIVE] ⚠️  Coordinator 失效');
    const nodes = this.registry.getOnlineNodes();
    const result = this.failover.handleCoordinatorFailure(nodes);

    const isMe = this.localNode && result.coordinatorId === this.localNode.nodeId;
    if (isMe) {
      console.log('[HIVE] 🎯 本节点提升为 Coordinator');
    } else {
      console.log(`[HIVE] ✓ 新 Coordinator: ${result.coordinatorName}`);
    }
  }

  /**
   * 优雅退出
   */
  private setupSignalHandlers(): void {
    const shutdown = () => {
      if (!this.isRunning) return;
      this.isRunning = false;

      console.log('\n[HIVE] 正在关闭节点...');

      this.mdns?.shutdown();
      this.p2p?.shutdown();

      console.log('[HIVE] ✓ 节点已关闭\n');
      process.exit(0);
    };

    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);
  }

  /**
   * 根据 tier 获取默认 Agent
   */
  private getDefaultAgents(tier: NodeTier): string[] {
    switch (tier) {
      case 'cloud':
        return ['researcher', 'architect', 'reporter', 'coder', 'tester'];
      case 'local':
        return ['coder', 'tester', 'reviewer', 'docs', 'ops'];
      case 'edge':
        return ['secretary', 'sm'];
      default:
        return ['coder'];
    }
  }
}

// ============================================================
// CLI 命令解析
// ============================================================

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  const cli = new HiveNodeCLI();

  switch (command) {
    case 'start': {
      const config: NodeConfig = {};

      // 解析参数
      for (let i = 1; i < args.length; i++) {
        const arg = args[i];
        if (arg.startsWith('--name=')) {
          config.name = arg.split('=')[1];
        } else if (arg.startsWith('--tier=')) {
          config.tier = arg.split('=')[1] as NodeTier;
        } else if (arg.startsWith('--port=')) {
          config.port = parseInt(arg.split('=')[1]);
        } else if (arg.startsWith('--agents=')) {
          config.agents = arg.split('=')[1].split(',');
        }
      }

      await cli.start(config);
      break;
    }

    case 'status': {
      cli.status();
      break;
    }

    case 'peers': {
      cli.peers();
      break;
    }

    default: {
      console.log(`
HIVE Node CLI - Solar Community Neural Network

用法:
  bun core/hive/cli/node.ts <command> [options]

命令:
  start       启动节点
    --name=<名称>         节点名称 (默认: Solar-<hostname>)
    --tier=<层级>         节点层级 (cloud/local/edge, 默认: local)
    --port=<端口>         监听端口 (默认: 9876)
    --agents=<Agent列表>  能力列表 (逗号分隔, 如: coder,tester)

  status      查看节点状态
  peers       列出已发现的节点

示例:
  bun core/hive/cli/node.ts start --name="我的节点"
  bun core/hive/cli/node.ts start --tier=cloud --agents=researcher,coder
  bun core/hive/cli/node.ts status
  bun core/hive/cli/node.ts peers
      `);
      break;
    }
  }
}

main().catch(console.error);
