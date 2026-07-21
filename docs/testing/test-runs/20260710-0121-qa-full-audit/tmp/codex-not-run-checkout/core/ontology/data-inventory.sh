#!/bin/bash
# Solar Data Inventory - 数据资产盘点
# 每次 personality-learner 或任务开始前调用

DB_FILE="$HOME/.solar/solar.db"

echo "┌─────────────────────────────────────────────────────────────────┐"
echo "│                   📊 Solar 数据资产状态                          │"
echo "├─────────────────────────────────────────────────────────────────┤"

# 显示资产统计
sqlite3 -separator '|' "$DB_FILE" "
SELECT 
    asset_type,
    COUNT(*),
    SUM(record_count),
    SUM(size_bytes)/1024/1024
FROM sys_data_assets
GROUP BY asset_type;
" | while IFS='|' read -r type count records size_mb; do
    printf "│  %-10s  %3s 资产  %10s 记录  %6s MB           │\n" "$type" "$count" "$records" "$size_mb"
done

echo "├─────────────────────────────────────────────────────────────────┤"
# 总计
TOTAL=$(sqlite3 "$DB_FILE" "SELECT SUM(record_count) FROM sys_data_assets;")
printf "│  总计: %s 条记录                                         │\n" "$TOTAL"
echo "└─────────────────────────────────────────────────────────────────┘"

# 返回总记录数，供调用者使用
echo "$TOTAL"
