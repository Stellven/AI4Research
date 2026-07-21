#!/bin/bash
# HIVE Phase 2 Demo
# 演示节点发现和 Coordinator 选举

echo "==================================================="
echo "     HIVE Phase 2 Demo"
echo "     节点发现 + Coordinator 选举"
echo "==================================================="
echo ""

# 检查依赖
if ! command -v bun &> /dev/null; then
    echo "❌ 需要安装 Bun"
    exit 1
fi

echo "启动演示 (需要 2 个终端窗口)"
echo ""
echo "终端 1 (当前窗口):"
echo "  bun core/hive/cli/node.ts start --name=\"节点1\""
echo ""
echo "终端 2 (新窗口):"
echo "  bun core/hive/cli/node.ts start --name=\"节点2\" --port=9877"
echo ""
echo "预期结果:"
echo "  1. 节点1 启动并广播"
echo "  2. 节点2 启动并发现节点1"
echo "  3. 自动建立 P2P 连接"
echo "  4. 执行 Coordinator 选举"
echo "  5. 显示选举结果 (评分最高者当选)"
echo ""
echo "按 Enter 启动节点1..."
read

bun core/hive/cli/node.ts start --name="节点1"
