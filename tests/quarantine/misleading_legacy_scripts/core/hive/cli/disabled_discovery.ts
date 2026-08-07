#!/usr/bin/env bun
/**
 * HIVE Discovery Test
 * 测试 mDNS 和 P2P 功能
 */

import { MDNSDiscovery } from '../discovery/mdns';
import { P2PTransport } from '../transport/p2p';
import { randomUUID } from 'crypto';
import type { HiveNode } from '../types';

async function testMDNS() {
  console.log('\n=== 测试 mDNS 发现 ===\n');

  const mdns = new MDNSDiscovery();

  // 创建测试节点
  const testNode: HiveNode = {
    nodeId: randomUUID(),
    name: 'Test-Node-1',
    owner: 'test',
    tier: 'local',
    capabilities: [],
    status: 'online',
    credits: 100,
    joinedAt: new Date(),
    lastHeartbeat: new Date(),
  };

  // 广播节点
  mdns.advertise(testNode, 9876);

  // 开始扫描
  let discovered = 0;
  mdns.startBrowsing({
    onPeerDiscovered: (peer) => {
      console.log(`✓ 发现节点: ${peer.name} (${peer.host}:${peer.port})`);
      console.log(`  Tier: ${peer.tier}, Status: ${peer.status}`);
      discovered++;
    },
    onPeerLost: (nodeId) => {
      console.log(`✗ 节点离线: ${nodeId}`);
    },
  });

  // 等待 10 秒
  console.log('扫描中... (10秒)');
  await new Promise(resolve => setTimeout(resolve, 10000));

  console.log(`\n发现 ${discovered} 个节点 (不包括自己)`);

  mdns.shutdown();
}

async function testP2P() {
  console.log('\n=== 测试 P2P 通信 ===\n');

  const nodeId1 = randomUUID();
  const nodeId2 = randomUUID();

  // 创建第一个节点
  const p2p1 = new P2PTransport({
    port: 9877,
    nodeId: nodeId1,
    onMessage: (msg, from) => {
      console.log(`[Node1] 收到消息: ${msg.type} from ${from}`);
    },
    onPeerConnected: (peerId, address) => {
      console.log(`[Node1] ✓ 节点连接: ${peerId} (${address})`);
    },
  });

  await p2p1.listen();

  // 创建第二个节点
  const p2p2 = new P2PTransport({
    port: 9878,
    nodeId: nodeId2,
    onMessage: (msg, from) => {
      console.log(`[Node2] 收到消息: ${msg.type} from ${from}`);
    },
    onPeerConnected: (peerId, address) => {
      console.log(`[Node2] ✓ 节点连接: ${peerId} (${address})`);
    },
  });

  await p2p2.listen();

  // Node2 连接 Node1
  console.log('\n连接节点...');
  await p2p2.connect(nodeId1, 'localhost', 9877);

  // 等待连接建立
  await new Promise(resolve => setTimeout(resolve, 1000));

  // 发送测试消息
  console.log('\n发送心跳消息...');
  p2p2.send(nodeId1, 'HEARTBEAT', {
    nodeId: nodeId2,
    timestamp: new Date(),
  });

  // 等待消息
  await new Promise(resolve => setTimeout(resolve, 2000));

  // 清理
  p2p1.shutdown();
  p2p2.shutdown();
}

async function main() {
  const test = process.argv[2] || 'mdns';

  try {
    if (test === 'mdns') {
      await testMDNS();
    } else if (test === 'p2p') {
      await testP2P();
    } else {
      console.log(`
用法: bun test-discovery.ts [mdns|p2p]

  mdns  测试 mDNS 节点发现 (默认)
  p2p   测试 P2P 通信
      `);
    }
  } catch (err) {
    console.error('测试失败:', err);
    process.exit(1);
  }
}

main();
