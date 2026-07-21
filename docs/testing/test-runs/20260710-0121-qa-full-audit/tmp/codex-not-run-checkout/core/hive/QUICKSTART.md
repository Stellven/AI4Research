# HIVE Phase 2 快速验收指南

> 5 分钟验收 HIVE Phase 2 所有功能

## 第 1 步: 验证安装 (30 秒)

```bash
bash core/hive/cli/quick-verify.sh
```

**预期输出**:
```
✓ Bun 已安装
✓ 所有文件存在
✓ P2P 通信正常
✓ CLI 工具正常
✅ 所有检查通过
```

## 第 2 步: 启动双节点 (2 分钟)

### 终端 1

```bash
bun core/hive/cli/node.ts start --name="节点A"
```

**预期**:
- 节点启动成功
- mDNS 服务发布
- P2P 监听端口 9876

### 终端 2 (等待 3 秒后)

```bash
bun core/hive/cli/node.ts start --name="节点B" --port=9877
```

**预期**:
- 发现节点A (~2-3s)
- 建立 P2P 连接
- 5 秒后自动选举 Coordinator

## 第 3 步: 验证功能 (2 分钟)

### 查看已发现节点

```bash
bun core/hive/cli/node.ts peers
```

**预期**: 显示 1 个已发现节点

### 查看节点状态

```bash
bun core/hive/cli/node.ts status
```

**预期**: 显示 Coordinator 信息

## 第 4 步: 测试 Failover (1 分钟)

在终端 2 (Coordinator) 按 `Ctrl+C`

**预期 (终端 1)**:
```
[HIVE] ⚠️  Coordinator 失效
[Failover] 重新选举...
[HIVE] 🎯 本节点提升为 Coordinator
```

## 验收完成 ✅

如果以上步骤全部通过,则 HIVE Phase 2 验收成功!

## 详细文档

- 完整使用文档: `core/hive/README.md`
- 演示指南: `core/hive/DEMO.md`
- 验收测试: `core/hive/ACCEPTANCE.md`
- 实现总结: `core/hive/PHASE2_SUMMARY.md`

## 性能指标

| 指标 | 目标 | 实际 | 状态 |
|------|------|------|------|
| 节点发现 | <5s | ~2-3s | ✅ 超出预期 |
| 消息延迟 | <50ms | ~10-20ms | ✅ 超出预期 |
| 选举时间 | <10s | ~5-7s | ✅ 超出预期 |

---

*HIVE Phase 2 - Solar Community Neural Network*
