#!/bin/bash
# Solar Startup Check - 检查外部依赖状态，生成启动宣告
# 用于 SessionStart Hook

set -euo pipefail

DEPS_FILE="$HOME/Solar/core/bootstrap/external-deps.json"
DB_FILE="$HOME/.solar/solar.db"

# ==================== 检查后台服务 ====================
check_services() {
    local issues=""
    local running=0
    local stopped=0

    # 缓存 launchctl 输出，避免多次调用
    local launchctl_output
    launchctl_output=$(launchctl list 2>/dev/null || true)

    # 检查关键服务
    local services=("mail-agent" "ontology-reflector" "hn-monitor" "memory-consolidator" "personality-learner")

    for svc in "${services[@]}"; do
        if echo "$launchctl_output" | grep -q "com.solar.${svc}"; then
            ((running++)) || true
        else
            ((stopped++)) || true
            issues+="  • $svc 未运行\n"
        fi
    done

    echo "$running|$stopped|$issues"
}

# ==================== 检查初始化任务 ====================
check_init_tasks() {
    local pending=""
    local count=0

    # 检查本体 v2 表是否存在
    if ! sqlite3 "$DB_FILE" ".tables" 2>/dev/null | grep -q "evo_memory_core"; then
        pending+="  • 创建本体 v2 表: sqlite3 ~/.solar/solar.db < ~/Solar/core/ontology/schema-v2.sql\n"
        ((count++))
    fi

    # 检查 A人格快照是否存在
    if ! sqlite3 "$DB_FILE" "SELECT 1 FROM sys_personality_snapshots WHERE personality_id='jingang_barbie' LIMIT 1;" 2>/dev/null | grep -q "1"; then
        pending+="  • 备份 A 人格 (实验保护)\n"
        ((count++))
    fi

    # 检查 Big Five 表
    if ! sqlite3 "$DB_FILE" ".tables" 2>/dev/null | grep -q "sys_personality_big_five"; then
        pending+="  • 创建 Big Five 人格表\n"
        ((count++))
    fi

    echo "$count|$pending"
}

# ==================== 检查数据积累 ====================
check_data() {
    local episodic=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM evo_memory_episodic;" 2>/dev/null || echo "0")
    local semantic=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM evo_memory_semantic;" 2>/dev/null || echo "0")
    local procedural=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM evo_memory_procedural;" 2>/dev/null || echo "0")

    echo "$episodic|$semantic|$procedural"
}

# ==================== 生成启动宣告 ====================
generate_announcement() {
    # 检查各项状态
    IFS='|' read -r svc_running svc_stopped svc_issues <<< "$(check_services)"
    IFS='|' read -r init_count init_pending <<< "$(check_init_tasks)"
    IFS='|' read -r mem_ep mem_sem mem_proc <<< "$(check_data)"

    # 构建宣告
    local announcement=""

    # 如果有需要监护人处理的事项
    if [[ $svc_stopped -gt 0 ]] || [[ $init_count -gt 0 ]]; then
        announcement+="【⚠️ 需要监护人协助】\n"
        announcement+="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

        if [[ $svc_stopped -gt 0 ]]; then
            announcement+="后台服务 ($svc_running 运行 / $svc_stopped 停止):\n"
            announcement+="$svc_issues"
        fi

        if [[ $init_count -gt 0 ]]; then
            announcement+="待初始化任务 ($init_count 项):\n"
            announcement+="$init_pending"
        fi

        announcement+="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        announcement+="执行: ~/Solar/core/bootstrap/setup-all.sh\n"
    fi

    # 数据积累状态
    announcement+="\n【记忆状态】 E:$mem_ep / S:$mem_sem / P:$mem_proc\n"

    echo -e "$announcement"
}

# ==================== 主函数 ====================
main() {
    generate_announcement
}

main "$@"
