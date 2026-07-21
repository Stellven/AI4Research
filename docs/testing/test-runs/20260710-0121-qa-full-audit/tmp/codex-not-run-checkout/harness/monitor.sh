#!/bin/bash
# ================================================================
# Solar Harness — 指挥中心 + 协调器 (Command Center + Coordinator)
#
# 功能: 状态监控 + 自动协同调度 + 快捷命令
# 协调器在后台轮询 sprint 状态变化，自动向 pane 派发任务
# @module solar-farm/harness
# ================================================================
HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"

# 启动协调器后台进程
COORD_PID=""
start_coordinator() {
  # 先杀旧进程
  if [[ -f "$HARNESS_DIR/.coordinator.pid" ]]; then
    local old_pid
    old_pid=$(cat "$HARNESS_DIR/.coordinator.pid")
    # Sprint 20260420-082442 D2: kill-0 验活，不盲目 kill
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
      kill "$old_pid" 2>/dev/null && sleep 1
    else
      rm -f "$HARNESS_DIR/.coordinator.pid"
    fi
  fi
  # 清除残留状态和旧日志
  rm -f "$HARNESS_DIR/.coordinator-state"
  : > "$HARNESS_DIR/.coordinator.log"

  # Sprint 20260420-082442 D2: 不预写 pidfile，coordinator 自己管
  if [[ -f "$HARNESS_DIR/coordinator.sh" ]]; then
    bash "$HARNESS_DIR/coordinator.sh" >> "$HARNESS_DIR/.coordinator.log" 2>&1 &
    COORD_PID=$!
  fi
}

stop_coordinator() {
  if [[ -n "$COORD_PID" ]]; then
    kill "$COORD_PID" 2>/dev/null
  elif [[ -f "$HARNESS_DIR/.coordinator.pid" ]]; then
    kill "$(cat "$HARNESS_DIR/.coordinator.pid")" 2>/dev/null
  fi
  rm -f "$HARNESS_DIR/.coordinator.pid"
}

trap stop_coordinator EXIT

# 启动协调器
start_coordinator

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'; B='\033[0;34m'; W='\033[1;37m'; N='\033[0m'
DIM='\033[2m'

# 获取最新 sprint 状态
get_latest_sprint() {
  local latest=""
  for f in "$SPRINTS_DIR"/*.status.json; do
    [[ -f "$f" ]] || continue
    latest="$f"
  done
  echo "$latest"
}

get_sprint_field() {
  local f="$1" field="$2"
  python3 -c "import json; print(json.load(open('$f')).get('$field',''))" 2>/dev/null
}

# 显示主界面
show_dashboard() {
  clear
  echo -e "${C}╔════════════════════════════════════════════════╗${N}"
  echo -e "${C}║${W}  Solar Harness — 指挥中心${N}                    ${C}║${N}"
  echo -e "${C}╚════════════════════════════════════════════════╝${N}"
  echo ""

  # --- Harness 状态 ---
  if tmux has-session -t solar-harness 2>/dev/null; then
    echo -e "  ${G}● Harness 运行中${N}  $(date '+%H:%M:%S')"
  else
    echo -e "  ${R}○ Harness 未运行${N}"
  fi
  echo ""

  # --- Sprint 状态 ---
  local sf
  sf=$(get_latest_sprint)

  if [[ -z "$sf" ]]; then
    echo -e "${Y}  ━━ 当前无 Sprint ━━${N}"
    echo ""
    echo -e "${W}  建议操作:${N}"
    echo ""
    echo -e "  ${G}1.${N} 创建新 Sprint:"
    echo -e "     ${DIM}~/.solar/bin/solar-harness sprint \"你的需求描述\"${N}"
    echo ""
    echo -e "  ${G}2.${N} 或在规划者窗口直接描述需求"
    echo ""
  else
    local sid st round title
    sid=$(get_sprint_field "$sf" "id")
    st=$(get_sprint_field "$sf" "status")
    round=$(get_sprint_field "$sf" "round")
    title=$(get_sprint_field "$sf" "title")

    # 如果 status.json 没有 title，从 contract.md 提取需求描述
    if [[ -z "$title" ]]; then
      local contract="${SPRINTS_DIR}/${sid}.contract.md"
      if [[ -f "$contract" ]]; then
        title=$(sed -n '/^## 需求/,/^##/{/^## 需求/d;/^##/d;/^$/d;p;}' "$contract" | head -1 | sed 's/^[[:space:]]*//')
      fi
    fi
    [[ -z "$title" ]] && title="$sid"

    # 状态颜色
    case "$st" in
      drafting)          sc="$Y"; icon="📝"; label="草稿中" ;;
      active)            sc="$C"; icon="📋"; label="待计划" ;;
      planning)          sc="$Y"; icon="📐"; label="计划审批中" ;;
      approved)          sc="$C"; icon="🔨"; label="实现中" ;;
      reviewing|ready_for_review) sc="$B"; icon="🔍"; label="代码评审中" ;;
      passed|done)       sc="$G"; icon="✅"; label="已完成" ;;
      failed)            sc="$R"; icon="❌"; label="失败" ;;
      failed_review)     sc="$R"; icon="🔄"; label="打回修改中" ;;
      interrupted)       sc="$R"; icon="⏸"; label="已中断" ;;
      *)                 sc="$N"; icon="❓"; label="$st" ;;
    esac

    echo -e "${Y}  ━━ 当前 Sprint ━━${N}"
    echo -e "  ${icon} ${W}${title}${N}"
    echo -e "  ${DIM}${sid}${N}"
    echo -e "  状态: ${sc}${label}${N}  轮次: ${round}"
    echo ""

    # --- 根据状态推荐操作 ---
    echo -e "${W}  ━━ 推荐操作 ━━${N}"
    echo ""

    case "$st" in
      drafting)
        echo -e "  ${G}→${N} 规划者需要展开 Done 定义"
        echo ""
        echo -e "  切到 ${C}规划者窗口${N} (Ctrl+B → ↑←)，输入:"
        echo ""
        echo -e "  ${DIM}──────────────────────────────────────${N}"
        echo -e "  ${W}读取 ~/.solar/harness/sprints/${sid}.contract.md${N}"
        echo -e "  ${W}展开 Done 定义，写清楚可检查的条件${N}"
        echo -e "  ${W}完成后更新 status.json 为 active${N}"
        echo -e "  ${DIM}──────────────────────────────────────${N}"
        echo ""
        echo -e "  ${DIM}(可以选中上面三行，拷贝粘贴到规划者窗口)${N}"
        ;;

      active)
        echo -e "  ${G}→${N} 建设者需要实现代码"
        echo ""
        echo -e "  切到 ${C}建设者窗口${N} (Ctrl+B → ↑→)，输入:"
        echo ""
        echo -e "  ${DIM}──────────────────────────────────────${N}"
        echo -e "  ${W}读取 ~/.solar/harness/sprints/${sid}.contract.md${N}"
        echo -e "  ${W}按 Done 定义实现代码，写 handoff 文档${N}"
        echo -e "  ${W}完成后更新 status.json 为 reviewing${N}"
        echo -e "  ${DIM}──────────────────────────────────────${N}"
        ;;

      reviewing)
        echo -e "  ${G}→${N} 审判官需要评估代码"
        echo ""
        echo -e "  切到 ${C}审判官窗口${N} (Ctrl+B → ↓←)，输入:"
        echo ""
        echo -e "  ${DIM}──────────────────────────────────────${N}"
        echo -e "  ${W}读取 ~/.solar/harness/sprints/${sid}.contract.md${N}"
        echo -e "  ${W}读取 ~/.solar/harness/sprints/${sid}.handoff.md${N}"
        echo -e "  ${W}逐条检查 Done，写 eval.md 评估报告${N}"
        echo -e "  ${DIM}──────────────────────────────────────${N}"
        ;;

      passed|done)
        echo -e "  ${G}Sprint 已完成!${N}"
        echo ""
        echo -e "  查看合约: ${DIM}cat ~/.solar/harness/sprints/${sid}.contract.md${N}"
        echo -e "  查看评估: ${DIM}cat ~/.solar/harness/sprints/${sid}.eval.md${N}"
        echo ""
        echo -e "  ${G}→${N} 创建新 Sprint:"
        echo -e "     ${DIM}~/.solar/bin/solar-harness sprint \"新需求\"${N}"
        ;;

      failed)
        echo -e "  ${R}Sprint 失败 (已超过最大轮次)${N}"
        echo ""
        echo -e "  查看评估: ${DIM}cat ~/.solar/harness/sprints/${sid}.eval.md${N}"
        echo ""
        echo -e "  ${G}→${N} 让规划者修正合约:"
        echo ""
        echo -e "  ${DIM}──────────────────────────────────────${N}"
        echo -e "  ${W}读取 ~/.solar/harness/sprints/${sid}.eval.md${N}"
        echo -e "  ${W}分析失败原因，修正合约或调整范围${N}"
        echo -e "  ${DIM}──────────────────────────────────────${N}"
        ;;

      interrupted)
        echo -e "  ${R}Sprint 被中断${N}"
        echo ""
        echo -e "  ${G}→${N} 恢复 Sprint:"
        echo ""
        echo -e "  ${DIM}──────────────────────────────────────${N}"
        echo -e "  ${W}python3 -c \"import json; d=json.load(open('~/.solar/harness/sprints/${sid}.status.json')); d['status']='active'; json.dump(d,open('~/.solar/harness/sprints/${sid}.status.json','w'),indent=2)\"${N}"
        echo -e "  ${DIM}──────────────────────────────────────${N}"
        ;;
    esac
  fi

  echo ""

  # --- 协调器状态 ---
  if [[ -n "$COORD_PID" ]] && kill -0 "$COORD_PID" 2>/dev/null; then
    echo -e "  ${G}● 协调器运行中${N} (PID: $COORD_PID) — 自动派发已启用"
  else
    echo -e "  ${R}○ 协调器未运行${N}"
  fi
  echo ""

  # --- 最近调度日志 ---
  if [[ -f "$HARNESS_DIR/.coordinator.log" ]]; then
    local log_lines
    log_lines=$(tail -3 "$HARNESS_DIR/.coordinator.log" 2>/dev/null)
    if [[ -n "$log_lines" ]]; then
      echo -e "${DIM}  最近调度:${N}"
      echo "$log_lines" | while read -r line; do
        echo -e "  ${DIM}${line}${N}"
      done
      echo ""
    fi
  fi

  # --- 快捷命令 ---
  echo -e "${Y}  ━━ 快捷命令 ━━${N}"
  echo ""
  echo -e "  ${G}n${N}) 新建 Sprint    ${G}s${N}) 查看全局状态    ${G}r${N}) 刷新"
  echo -e "  ${G}l${N}) 调度日志       ${G}c${N}) 查看检查点      ${G}q${N}) 退出"
  echo -e "  ${G}k${N}) 关闭 Harness   ${G}w${N}) Webhook 管理"
  echo ""

  # --- 底部 ---
  echo -e "${C}════════════════════════════════════════════════${N}"
}

# ---- 主循环 ----
# 确保从终端读取 (tmux pane 环境下 stdin 可能被重定向)
exec 0< /dev/tty 2>/dev/null || true

while true; do
  show_dashboard

  # 等待用户输入 (5秒超时自动刷新)
  if read -t 5 -r -s -n 1 key < /dev/tty 2>/dev/null; then
    case "$key" in
      n|N)
        echo -e "\n\n  ${W}输入需求描述:${N} "
        read -r req < /dev/tty
        [[ -n "$req" ]] && {
          ~/.solar/bin/solar-harness sprint "$req"
          echo -e "\n  ${G}已创建! 5秒后刷新...${N}"
          sleep 5
        }
        ;;
      s|S)
        ~/.solar/bin/solar-harness status
        echo -e "\n  ${DIM}按任意键返回...${N}"
        read -r -s -n 1 < /dev/tty
        ;;
      r|R)
        # 直接刷新
        ;;
      l|L)
        echo -e "\n${W}  ━━ 协调器调度日志 ━━${N}\n"
        tail -20 "$HARNESS_DIR/.coordinator.log" 2>/dev/null || echo "  (无日志)"
        echo -e "\n  ${DIM}按任意键返回...${N}"
        read -r -s -n 1 < /dev/tty
        ;;
      c|C)
        echo -e "\n${W}  ━━ Git 检查点 ━━${N}\n"
        git -C "$HOME/.claude" tag -l 'checkpoint/*' --sort=-creatordate 2>/dev/null | head -10 || echo "  (无检查点)"
        echo -e "\n  ${DIM}回滚: git checkout <tag> -- <files>${N}"
        echo -e "  ${DIM}按任意键返回...${N}"
        read -r -s -n 1 < /dev/tty
        ;;
      w|W)
        echo -e "\n${W}  ━━ Webhook 管理 ━━${N}\n"
        if [[ -f "$HARNESS_DIR/.webhook.pid" ]] && kill -0 "$(cat "$HARNESS_DIR/.webhook.pid")" 2>/dev/null; then
          echo -e "  ${G}● Webhook server 运行中${N} (PID: $(cat "$HARNESS_DIR/.webhook.pid"))"
          echo -e "  端口: ${HARNESS_PORT:-9876}"
          echo -e "  ${DIM}curl -X POST localhost:${HARNESS_PORT:-9876}/sprint -H 'Content-Type: application/json' -d '{\"title\":\"需求\"}'"
        else
          echo -e "  ${R}○ Webhook server 未运行${N}"
          echo -e "  启动: ${DIM}~/.solar/bin/solar-harness webhook start${N}"
        fi
        echo -e "\n  ${DIM}按任意键返回...${N}"
        read -r -s -n 1 < /dev/tty
        ;;
      k|K)
        echo -e "\n  ${Y}确认关闭 Harness? (y/n)${N} "
        read -r -s -n 1 confirm < /dev/tty
        [[ "$confirm" == "y" ]] && {
          ~/.solar/bin/solar-harness kill
          echo -e "\n  ${G}已关闭。按任意键退出...${N}"
          read -r -s -n 1 < /dev/tty
          exit 0
        }
        ;;
      q|Q)
        clear
        echo -e "${Y}  退出指挥中心。Harness 继续在后台运行。${N}"
        echo -e "  重新打开: ${C}~/.solar/bin/solar-harness${N}"
        exit 0
        ;;
    esac
  fi
done
