#!/bin/bash
# Quick Verification Script
# 快速验证 HIVE Phase 2 功能

set -e

echo "┌─────────────────────────────────────────────────────┐"
echo "│  HIVE Phase 2 Quick Verification                   │"
echo "└─────────────────────────────────────────────────────┘"
echo ""

# 检查依赖
echo "[1/4] 检查依赖..."
if ! command -v bun &> /dev/null; then
    echo "❌ 需要安装 Bun"
    exit 1
fi
echo "✓ Bun 已安装"

# 检查文件
echo ""
echo "[2/4] 检查文件..."
FILES=(
    "core/hive/discovery/mdns.ts"
    "core/hive/transport/p2p.ts"
    "core/hive/coordinator.ts"
    "core/hive/cli/node.ts"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✓ $file"
    else
        echo "❌ 缺少文件: $file"
        exit 1
    fi
done

# 运行 P2P 测试
echo ""
echo "[3/4] 运行 P2P 测试..."
if bun core/hive/cli/test-discovery.ts p2p 2>&1 | grep -q "收到消息: HEARTBEAT"; then
    echo "✓ P2P 通信正常"
else
    echo "❌ P2P 测试失败"
    exit 1
fi

# 检查 CLI 命令
echo ""
echo "[4/4] 检查 CLI..."
if bun core/hive/cli/node.ts 2>&1 | grep -q "HIVE Node CLI"; then
    echo "✓ CLI 工具正常"
else
    echo "❌ CLI 工具失败"
    exit 1
fi

echo ""
echo "┌─────────────────────────────────────────────────────┐"
echo "│  ✅ 所有检查通过                                    │"
echo "└─────────────────────────────────────────────────────┘"
echo ""
echo "下一步: 启动节点"
echo ""
echo "  终端 1:"
echo "    bun core/hive/cli/node.ts start --name=\"节点1\""
echo ""
echo "  终端 2:"
echo "    bun core/hive/cli/node.ts start --name=\"节点2\" --port=9877"
echo ""
