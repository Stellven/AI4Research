#!/bin/bash
# Solar Mail Agent - 后台邮件监听与自动执行
# 方案A: cron + himalaya + claude CLI

set -euo pipefail

# ==================== 配置 ====================
IFS=',' read -r -a GUARDIAN_EMAILS <<< "${SOLAR_GUARDIAN_EMAILS:-guardian@example.com}"
PROCESSED_FILE="$HOME/.solar/processed_mails.txt"
LOG_FILE="$HOME/.solar/agent-daemon.log"
LOCK_FILE="/tmp/solar-mail-agent.lock"
IMESSAGE_ADDR="${SOLAR_GUARDIAN_IMESSAGE:-guardian-imessage@example.com}"
MAIL_RECIPIENT="${SOLAR_ALERT_EMAIL:-${SOLAR_GUARDIAN_EMAIL:-${GUARDIAN_EMAILS[0]:-guardian@example.com}}}"

# ==================== 初始化 ====================
mkdir -p "$HOME/.solar"
touch "$PROCESSED_FILE"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# 防止重复运行
if [ -f "$LOCK_FILE" ]; then
    pid=$(cat "$LOCK_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        log "已有实例运行中 (PID: $pid)，退出"
        exit 0
    fi
fi
echo $$ > "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

# ==================== 核心函数 ====================

# 检查是否是监护人邮件
is_guardian_email() {
    local from="$1"
    for guardian in "${GUARDIAN_EMAILS[@]}"; do
        if [[ "$from" == *"$guardian"* ]]; then
            return 0
        fi
    done
    return 1
}

# 检查是否已处理
is_processed() {
    local mail_id="$1"
    grep -q "^${mail_id}$" "$PROCESSED_FILE" 2>/dev/null
}

# 标记为已处理
mark_processed() {
    local mail_id="$1"
    echo "$mail_id" >> "$PROCESSED_FILE"
}

# 发送 iMessage 回复
send_imessage() {
    local message="$1"
    osascript -e "tell application \"Messages\" to send \"$message\" to participant \"$IMESSAGE_ADDR\" of (1st account whose service type = iMessage)" >/dev/null 2>&1 || log "iMessage 发送失败"
}

# 发送 iMessage 照片
send_imessage_photo() {
    local photo_path="$1"
    osascript -e "tell application \"Messages\" to send POSIX file \"$photo_path\" to participant \"$IMESSAGE_ADDR\" of (1st account whose service type = iMessage)" >/dev/null 2>&1 || log "iMessage 照片发送失败"
}

# 发送邮件回复（支持附件）
send_email_reply() {
    local original_id="$1"
    local content="$2"
    local attachment="${3:-}"  # 可选附件路径，默认空

    # 转义内容中的特殊字符（双引号和反斜杠）
    local safe_content
    safe_content=$(echo "$content" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ' | head -c 500)

    if [[ -n "$attachment" && -f "$attachment" ]]; then
        # 带附件发送
        osascript -e "tell application \"Mail\" to set m to make new outgoing message with properties {subject:\"Re: Solar 执行结果\", content:\"$safe_content\", visible:false}" \
                  -e "tell application \"Mail\" to tell m to make new to recipient at end of to recipients with properties {address:\"$MAIL_RECIPIENT\"}" \
                  -e "tell application \"Mail\" to tell m to make new attachment with properties {file name:POSIX file \"$attachment\"} at after last paragraph" \
                  -e "tell application \"Mail\" to send m" >/dev/null 2>&1 || log "邮件发送失败"
    else
        # 无附件发送
        osascript -e "tell application \"Mail\" to set m to make new outgoing message with properties {subject:\"Re: Solar 执行结果\", content:\"$safe_content\", visible:false}" \
                  -e "tell application \"Mail\" to tell m to make new to recipient at end of to recipients with properties {address:\"$MAIL_RECIPIENT\"}" \
                  -e "tell application \"Mail\" to send m" >/dev/null 2>&1 || log "邮件发送失败"
    fi
}

# 执行任务，返回: result 和 photo_path (通过全局变量)
TASK_RESULT=""
TASK_PHOTO=""

execute_task() {
    local task="$1"
    local mail_id="$2"
    local task_lower=$(echo "$task" | tr '[:upper:]' '[:lower:]')

    log "执行任务: $task"
    TASK_RESULT=""
    TASK_PHOTO=""

    # 拍照任务 - 直接处理
    if [[ "$task_lower" == *"拍照"* || "$task_lower" == *"拍个照"* || "$task_lower" == *"照片"* || "$task_lower" == *"看看家"* ]]; then
        log "快捷任务: 拍照"
        local photo_file="$HOME/Desktop/solar_photo_$(date +%Y%m%d_%H%M%S).jpg"
        if imagesnap -w 1.5 "$photo_file" 2>/dev/null; then
            TASK_PHOTO="$photo_file"
            TASK_RESULT="📸 已拍照并附上"
            log "拍照成功: $TASK_PHOTO"
            return 0
        else
            TASK_RESULT="❌ 拍照失败"
            return 1
        fi
    fi

    # 天气任务
    if [[ "$task_lower" == *"天气"* || "$task_lower" == *"weather"* ]]; then
        log "快捷任务: 天气"
        TASK_RESULT="🌤️ $(curl -s 'wttr.in/?format=3' 2>/dev/null)"
        return 0
    fi

    # 时间任务
    if [[ "$task_lower" == *"时间"* || "$task_lower" == *"几点"* ]]; then
        log "快捷任务: 时间"
        TASK_RESULT="🕐 现在是 $(date '+%Y-%m-%d %H:%M:%S')"
        return 0
    fi

    # 其他任务 - 调用 Claude CLI (非交互模式)
    log "调用 Claude 处理复杂任务..."
    TASK_RESULT=$(cd ~/Solar && claude -p "$task" 2>&1 | head -100)
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log "Claude 执行失败，退出码: $exit_code"
        TASK_RESULT="执行出错 (exit $exit_code): $TASK_RESULT"
    fi

    # 如果结果为空，给个默认值
    if [[ -z "$TASK_RESULT" ]]; then
        TASK_RESULT="任务已收到，正在处理中..."
    fi
}

# ==================== 主逻辑 ====================

log "===== Solar Mail Agent 启动 ====="

# 获取最近的未读邮件
log "检查新邮件..."

# 用 JSON 格式获取邮件列表（更可靠）
mails_json=$(himalaya envelope list -o json 2>/dev/null) || {
    log "获取邮件列表失败"
    exit 1
}

# 解析 JSON，处理每封邮件
while read -r mail; do
    id=$(echo "$mail" | jq -r '.id')
    from=$(echo "$mail" | jq -r '.from.addr // .from.name // "unknown"')
    subject=$(echo "$mail" | jq -r '.subject // "(无主题)"')

    # 跳过空 ID
    [[ -z "$id" || "$id" == "null" ]] && continue

    # 跳过已处理
    if is_processed "$id"; then
        log "跳过已处理: $id"
        continue
    fi

    # 只处理监护人邮件
    if ! is_guardian_email "$from"; then
        log "跳过非监护人邮件: $id ($from)"
        mark_processed "$id"
        continue
    fi

    log "发现监护人邮件: $id - $subject"

    # 读取邮件内容
    content=$(himalaya message read "$id" 2>/dev/null) || {
        log "读取邮件内容失败: $id"
        continue
    }

    # 提取任务（主题 + 正文前200字）
    task="$subject"
    body=$(echo "$content" | tail -n +5 | head -20 | tr '\n' ' ')
    if [[ -n "$body" ]]; then
        task="$task: $body"
    fi

    # 执行任务
    log "开始执行: $task"
    execute_task "$task" "$id"

    # 发送结果 (转义特殊字符)
    safe_subject=$(echo "$subject" | tr -d '"')
    safe_result=$(echo "$TASK_RESULT" | tr -d '"' | head -5)
    reply_msg="Solar 已执行任务: $safe_subject - 结果: $safe_result"

    # 同时发 iMessage 和邮件
    send_imessage "✅ 任务完成: $subject"

    # 如果有照片，发送带附件的邮件和 iMessage
    if [[ -n "$TASK_PHOTO" && -f "$TASK_PHOTO" ]]; then
        log "发送照片附件: $TASK_PHOTO"
        send_email_reply "$id" "$reply_msg" "$TASK_PHOTO"
        send_imessage_photo "$TASK_PHOTO"
    else
        send_email_reply "$id" "$reply_msg"
    fi

    # 标记已处理
    mark_processed "$id"

    log "任务完成: $id"

done < <(echo "$mails_json" | jq -c '.[]' | head -10)

log "===== 本轮检查完成 ====="
