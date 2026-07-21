/**
 * HIVE mDNS Discovery Service
 * 局域网节点自动发现
 */

import Bonjour, { Service, Browser } from 'bonjour-service';
import type { HiveNode } from '../types';

const SERVICE_TYPE = 'solar-hive';
const SERVICE_PROTOCOL = 'tcp';
const DEFAULT_PORT = 9876;

export interface DiscoveredPeer {
  nodeId: string;
  name: string;
  host: string;
  port: number;
  tier: string;
  status: string;
  capabilities: string[];
  discoveredAt: Date;
}

export class MDNSDiscovery {
  private bonjour: Bonjour;
  private service?: Service;
  private browser?: Browser;
  private peers = new Map<string, DiscoveredPeer>();
  private onPeerDiscovered?: (peer: DiscoveredPeer) => void;
  private onPeerLost?: (nodeId: string) => void;

  constructor() {
    this.bonjour = new Bonjour();
  }

  /**
   * 启动 mDNS 服务 - 广播自己的存在
   */
  advertise(node: HiveNode, port: number = DEFAULT_PORT): void {
    console.log(`[mDNS] 广播节点: ${node.name} (${node.nodeId})`);

    this.service = this.bonjour.publish({
      name: node.name,
      type: SERVICE_TYPE,
      protocol: SERVICE_PROTOCOL,
      port,
      txt: {
        nodeId: node.nodeId,
        tier: node.tier,
        status: node.status,
        capabilities: JSON.stringify(node.capabilities.map(c => c.agentId)),
        owner: node.owner,
      },
    });

    this.service.on('error', (err: Error) => {
      console.error('[mDNS] 广播错误:', err.message);
    });

    console.log(`[mDNS] ✓ 服务已发布: _${SERVICE_TYPE}._${SERVICE_PROTOCOL}.local:${port}`);
  }

  /**
   * 开始扫描其他节点
   */
  startBrowsing(callbacks: {
    onPeerDiscovered?: (peer: DiscoveredPeer) => void;
    onPeerLost?: (nodeId: string) => void;
  }): void {
    this.onPeerDiscovered = callbacks.onPeerDiscovered;
    this.onPeerLost = callbacks.onPeerLost;

    console.log('[mDNS] 开始扫描节点...');

    this.browser = this.bonjour.find({
      type: SERVICE_TYPE,
      protocol: SERVICE_PROTOCOL,
    });

    this.browser.on('up', (service: Service) => {
      const peer = this.parsePeer(service);
      if (peer) {
        this.peers.set(peer.nodeId, peer);
        console.log(`[mDNS] ✓ 发现节点: ${peer.name} (${peer.host}:${peer.port})`);
        this.onPeerDiscovered?.(peer);
      }
    });

    this.browser.on('down', (service: Service) => {
      const nodeId = service.txt?.nodeId;
      if (nodeId && this.peers.has(nodeId)) {
        console.log(`[mDNS] ✗ 节点离线: ${service.name} (${nodeId})`);
        this.peers.delete(nodeId);
        this.onPeerLost?.(nodeId);
      }
    });

    this.browser.on('error', (err: Error) => {
      console.error('[mDNS] 扫描错误:', err.message);
    });
  }

  /**
   * 获取已发现的节点列表
   */
  getPeers(): DiscoveredPeer[] {
    return Array.from(this.peers.values());
  }

  /**
   * 获取节点数量
   */
  getPeerCount(): number {
    return this.peers.size;
  }

  /**
   * 停止服务
   */
  shutdown(): void {
    console.log('[mDNS] 关闭服务...');

    if (this.browser) {
      this.browser.stop();
    }

    if (this.service) {
      this.bonjour.unpublishAll(() => {
        console.log('[mDNS] ✓ 服务已取消发布');
      });
    }

    this.bonjour.destroy();
    this.peers.clear();
  }

  /**
   * 解析 Service 为 Peer 对象
   */
  private parsePeer(service: Service): DiscoveredPeer | null {
    try {
      const txt = service.txt || {};
      const nodeId = txt.nodeId;

      if (!nodeId) {
        console.warn('[mDNS] 忽略无 nodeId 的服务:', service.name);
        return null;
      }

      // 解析地址
      const addresses = service.addresses || [];
      const host = addresses.find(addr => !addr.includes(':')) || addresses[0] || service.host;

      return {
        nodeId,
        name: service.name,
        host,
        port: service.port || DEFAULT_PORT,
        tier: txt.tier || 'local',
        status: txt.status || 'online',
        capabilities: txt.capabilities ? JSON.parse(txt.capabilities) : [],
        discoveredAt: new Date(),
      };
    } catch (err) {
      console.error('[mDNS] 解析 Peer 失败:', err);
      return null;
    }
  }
}
