# Architect Investigation #002 — Dispatch 覆盖 Bug

**调研者**: 架构师化身 (pane 3, opus)
**问题**: 协调器 30s 内连派 2 个 dispatch 给 builder pane 0.1, 后派覆盖前派, 102743 被丢
**TL;DR**: dispatch_to_pane **没有 per-pane busy 互斥**, 只靠 idle prompt (`❯`) 检测. 当前一个 dispatch 的 send-keys 文本仍卡输入框 (Enter 被吞 / verify 失败) 时, 下一轮 dispatch 的**预解锁 C-u 会清掉残留**, 让前一个永远进不到 builder.

---

## 1. 现象时间线

| Time | 事件 |
|------|------|
| 10:27:43 | 102743 contract created (规划者基于 investigation-001 起 sprint 修 scanner) |
| 10:29:08 | 102743 status: drafting → active |
| 10:29:21 | iter N: get_latest=102743, handle_active 调 dispatch_to_pane(pane 0.1) |
| 10:29:34 | dispatch_to_pane 完成 send-keys, 文本入输入框 (verify 阶段) |
| 10:29:46 | iter N+2: 100705 mtime 被更新 → get_latest=100705, 触发 dispatch |
| 10:29:52 | dispatch_to_pane 给 100705: 预解锁 **C-u 清掉 102743 文本** → send 100705 → builder 跑 100705 |

**结果**: pane 0.1 跑 100705, 102743.dispatch.md 还在磁盘 (1284 bytes), 但 builder 从未读到.

---

## 2. 5 问答 (任务 B 关注点)

| # | 问题 | 答 |
|---|------|---|
| 1 | dispatch 检查 pane busy? | **半否**. 只检测 `❯[[:space:]]*$` (idle) 和 `✻ Baked` (thinking). 不知道 "pane 当前归哪个 sprint". 见 coord.sh:212 |
| 2 | 有 dispatch 队列? | **否**. 主循环每 iter 直接同步阻塞 ~5-15s 调 dispatch_to_pane. coord.sh:1900-1960 |
| 3 | 主循环每轮派多次? | **否, 单轮单 sprint**. get_latest_sprint_file 单返回. iter 间隔 ~10s, 跨 iter 累计可派多次 |
| 4 | 文件写盘 vs send-keys race? | 关键不是文件 race, 是**输入框 race** (单一资源被两套机制争用) |
| 5 | 需要 dispatch lock? | **是**. 不仅文件锁, 是逻辑锁: pane 进入"已派未确认"中间态时不能再派 |

---

## 3. 三个设计漏洞 (根因)

**漏洞 A — 无 per-pane 占用记录** (coord.sh:370-490)
- 协调器没有"pane X 当前归 sprint Y"的状态
- 看到 `❯` 就认为可派, 但 `❯` 出现的瞬间不代表 builder "干完了上一个 sprint"

**漏洞 B — 预解锁 C-u 是破坏性的** (coord.sh:408-422)
- 设计意图: 清掉输入框残留 (上次失败 dispatch / 用户误输入)
- 实际后果: 也清掉**前一次 dispatch 还未被 Enter 提交的合法文本**
- 后果: send-keys 在视觉上是"追加"语义, C-u 让它变"覆盖"语义

**漏洞 C — verify 双命中仍可被骗** (coord.sh:432-460)
- send-keys 文本进输入框 → verify capture 看见 keyword (即便没 Enter)
- builder pane 此时可能还显示**前一个任务**的 ✻ processing 特征
- 双命中 → 误判派发成功 → return 0
- 实际: builder 干旧活, 输入框躺着没人消费的新文本

---

## 4. 修复建议

### P0 — per-pane assignment tracking (推荐立即做)

```bash
# coordinator.sh 顶部
declare -A PANE_CURRENT_SPRINT=()  # idx → sid
declare -A PANE_ASSIGN_TS=()       # idx → 派出时间

dispatch_to_pane() {
  local pane="$1" sid="${3:-dispatch}"
  local pane_idx="${pane##*.}"
  local current_sid="${PANE_CURRENT_SPRINT[$pane_idx]:-}"

  if [[ -n "$current_sid" ]] && [[ "$current_sid" != "$sid" ]]; then
    local elapsed=$(( $(date +%s) - ${PANE_ASSIGN_TS[$pane_idx]:-0} ))
    if (( elapsed < 1800 )); then  # 30 min 内不抢占
      log "[dispatch] pane ${pane} 归 ${current_sid}, 拒派 ${sid}"
      return 2  # 区别返回码: 2 = 阻塞 (调用方放回队列), 1 = 真失败
    fi
    log "[dispatch] pane ${pane} 占用超时, 强制重派"
  fi
  # ... 原逻辑 ...
  PANE_CURRENT_SPRINT[$pane_idx]="$sid"
  PANE_ASSIGN_TS[$pane_idx]=$(date +%s)
}

# handle_passed/handle_failed 末尾:
clear_pane_assignment() {
  local sid="$1"
  for idx in "${!PANE_CURRENT_SPRINT[@]}"; do
    [[ "${PANE_CURRENT_SPRINT[$idx]}" == "$sid" ]] && {
      unset 'PANE_CURRENT_SPRINT[$idx]' 'PANE_ASSIGN_TS[$idx]'
    }
  done
}
```

**调用方处理 return 2** (handle_active 等):
```bash
dispatch_to_pane ... ; rc=$?
if [[ $rc -eq 2 ]]; then
  log "pane busy, 下轮再派"
  return 0  # 不 save_state, 让下轮 check_state_changed 再触发
fi
```

**持久化**: `declare -A` 进程变量协调器重启会丢. 写到 `~/.solar/harness/.pane-assignments` (key=value 行), 启动时 reload (同 `.coordinator-state`).

改动量: ~60 行 coord.sh + 1 个新文件.

### P1 — per-pane flock (防并发, 与 P0 互补)

```bash
dispatch_to_pane() {
  local pane_idx="${pane##*.}"
  local lock_file="$HARNESS_DIR/.dispatch-pane-${pane_idx}.lock"
  exec {lock_fd}>"$lock_file"
  if ! flock -n "$lock_fd"; then
    log "[dispatch] pane ${pane} 锁忙"
    return 2
  fi
  # ... 原逻辑 ...
  flock -u "$lock_fd"; exec {lock_fd}>&-
}
```

防"两个协调器进程同时 dispatch" (理论, 实际单实例不易触发). 改动量 ~15 行.

### P2 — dispatch queue 模型 (Phase A.2 后续, 不立即做)

主循环不直调 dispatch_to_pane, 改写"派发请求"到 `.dispatch-queue/`, 后台 dispatcher worker 单线程消费.

好处: 严格串行, 主循环不被 dispatch 阻塞, 队列可持久化.
代价: 新进程 + watchdog 关系 + ~200 行新代码.

**结论**: 当前 P0 + P1 已足够阻断本次 bug 类型, P2 留 Phase A.2.

---

## 5. 额外建议 (间接相关)

- **verify 强化**: 当前 keyword + processing 双命中可能被旧 task 残留欺骗. 改成 verify 时 capture 必须含**本次 dispatch 的 sid 字符串** (sid 在 dispatch.md 文件名, builder 读取后必然显示)
- **失败状态回滚**: dispatch_failed 时仅 emit_event, 但 `.coordinator-state` 已 save 新状态. 应回滚 cache 让下轮重试

---

## 6. 推荐路径

| 优先级 | 改动量 | sprint 建议 |
|--------|--------|------------|
| **P0 (per-pane assignment)** | ~60 行 + 持久化文件 | 起 sprint, 与 102743 (scanner fix) 不冲突, 可并行 |
| P1 (flock) | ~15 行 | 同 P0 sprint 一起做, 互补 |
| P2 (queue) | ~200 行新进程 | 待 Phase A.2 |

**引用 coord.sh**: 212, 370-490, 408-422, 432-460, 1900-1960.
