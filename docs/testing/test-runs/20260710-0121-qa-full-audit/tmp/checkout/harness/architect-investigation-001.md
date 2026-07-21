# Architect Investigation #001 — 协调器派单缺失根因

**调研者**: 架构师化身 (pane 3, opus)
**时间**: 2026-05-03T14:18Z
**问题**: 协调器有 4 个 active sprint 但只派出 2 个 dispatch
**结论 (TL;DR)**: `get_latest_sprint_file()` 是**单 sprint 扫描器**, 同一秒内多个 sprint 翻 active 时只有 mtime 最新的会被派, 其余永远 stuck.

---

## 1. 现状快照 (调研当时)

| Sprint | mtime (UTC) | status (file) | state cache | dispatch 文件 |
|--------|-------------|---------------|-------------|---------------|
| sprint-20260503-090450 | 13:58:44 | active | drafting ❌ | **缺失** |
| sprint-20260503-093223 | 13:58:46 | active | drafting ❌ | **缺失** |
| sprint-20260503-094659 | 13:58:49 | active | active ✅ | 09:58 已派 |
| sprint-20260503-100705 | 14:07:53 | active→planning | active ✅ | 10:08 已派 |

cache 文件: `~/.solar/harness/.coordinator-state` (per-sprint dict)
`090450:drafting|093223:drafting|094659:active|...|100705:active`

**关键不一致**: 090450 和 093223 的 status.json 已 `active`, 但 cache 还停在 `drafting` — 说明 coordinator **从来没看见过它们的状态变更**.

---

## 2. 根因 — get_latest_sprint_file 单点扫描

**代码位置**: `coordinator.sh:74-103`

```bash
get_latest_sprint_file() {
  local best="" best_mtime=0
  for f in ...; do
    local mtime=$(stat -f %m "$f")
    if [[ "$mtime" -gt "$best_mtime" ]]; then
      best_mtime="$mtime"; best="$f"
    fi
  done
  echo "$best"   # ← 只返回 1 个文件!
}
```

**主循环** (line 1900-1960): 每轮只调用 1 次 `get_latest_sprint_file` → 只检查 1 个 sprint 的状态变更.

### 时间线复盘 (案发现场)

```
13:58:44  090450.status.json mtime → active (规划者批准)
13:58:46  093223.status.json mtime → active (规划者批准, 比 090450 新 2s)
13:58:49  094659.status.json mtime → active (规划者批准, 最新)

13:58:5x  协调器 iter (~12s 周期):
          get_latest_sprint_file → 094659 (mtime 最大)
          check_state_changed(094659, active) → drafting→active, true
          handle_active → dispatch ✅
          save_state(094659:active)

13:59-14:07  协调器 iter:
          get_latest → 还是 094659 (mtime 不变)
          check_state_changed → 已是 active, false
          *** 090450 / 093223 完全没被扫到 ***
          它们的 mtime (13:58:44/46) 永远不会比 094659 (13:58:49) 大

14:07:53  100705.status.json mtime → active (新需求落地, 最新)

14:07:5x  协调器 iter:
          get_latest → 100705
          check_state_changed → drafting→active, true
          handle_active → dispatch ✅
```

**为什么 094659 之后还能轮到 100705**: 100705 是 14:07 新建合约, mtime > 094659. 但 090450 / 093223 的 mtime 一旦定格, 任何更新的 sprint 都会盖过它们 → **永远孤儿**.

### 为什么 check_state_changed 是 per-sprint 仍救不了

`check_state_changed` 看的是 **当前传入 sid + 当前 cache**, 设计上确实 per-sprint 正确. 问题在**它从来没被传入 090450 / 093223**, 因为 scanner 根本没把这俩文件交给主循环.

设计意图错配:
- `check_state_changed`: 假设主循环会**逐个**扫描所有 sprint
- `get_latest_sprint_file`: 实际只扫**一个最新的**

两者拼起来就是: 同一时刻最多只能感知 1 个 sprint 状态变更.

---

## 3. 次要噪音 (非阻塞但污染)

### 3.1 损坏 status.json (sprint-20260502-214730, -215801)

```python
{'status': 'drafting', 'title': 'save_state 写冒号 bug 修复', ...}
# ← 缺 'id' 字段
```

后果: 每 12s 协调器 log 写 2 行 `corrupted status.json skipped`, 每分钟约 10 行污染. **不阻塞派单**, 但 log 30 分钟就翻 300 行无效消息, 排查时刷屏.

修复: 删除这 2 个文件 (它们是手抖产物, 没 id 也无法被任何流程消费).

### 3.2 planner-review-drafting.sh line 44 算术错误

```bash
done_count=$(grep -c '^\- \[ \] \*\*D' "$local_cf" 2>/dev/null || echo "0")
# bug: grep -c 找不到时 stdout 写 "0\n" 然后 exit 1
#      || echo "0" 又追加 "0\n"
#      → done_count="0\n0" → [[ "$var" -ge 3 ]] arithmetic error
```

后果: drafting 阶段的**通知规划者**功能受影响 — 当合约 Done 数量不到 3 时进入 else 分支 (写 "Done 不足"), 但因 `[[ ]]` 报错先退出, 这条警告写不出. **不阻塞 active→builder 派发**.

修复: `grep -c ... 2>/dev/null || true` 即可 (grep -c 找不到时本来就输出 0).

### 3.3 pane 3 当前为 architect 保留

`choose_builder_pane()` 硬编码返回 `PANE_BUILDER` (pane 1), pane 3 不参与 builder 派发. 设计意图是**留给 architect 拓扑专用**, 已注释明确. 不参与本次根因, 但解释了为什么不能简单"加并行 builder pane 解决堆积".

---

## 4. 修复建议 (按优先级)

### P0 — 修 scanner: 单点 → 多点扫描

**思路 A (最小改动, 推荐)**: 主循环改成 for-loop 扫所有 sprint.

```bash
# 替换 get_latest_sprint_file + 单次 check_state_changed
# 改成: 每 iter 扫所有 status.json, 逐个 check_state_changed
for sf in "$SPRINTS_DIR"/sprint-*.status.json; do
  sid=$(get_field "$sf" "id"); st=$(get_field "$sf" "status")
  [[ -z "$sid" ]] && continue   # 跳损坏
  if check_state_changed "$sid" "$st"; then
    # 原 case "$st" in 派单逻辑保持不变
  fi
done
```

成本: ~20 行重构 main loop. 改动隔离在 `coordinator.sh` 1 处.
风险: 单 iter 扫描 ~80 个文件 × `python3 json` 解析 → 每轮多 ~200ms. 可加 `find -mtime -7d` 限制扫近期 7 天.

**思路 B (更稳)**: 保留 get_latest 做"最新派单优先级", 加一个 `scan_stuck_sprints()` 兜底, 每 5 轮 (60s) 扫一次孤儿.

代价: ~40 行新函数, 但兼容性最好.

### P1 — 清噪音

```bash
rm ~/.solar/harness/sprints/sprint-20260502-214730.status.json
rm ~/.solar/harness/sprints/sprint-20260502-215801.status.json
sed -i.bak 's|2>/dev/null || echo "0"|2>/dev/null || true|' \
  ~/.claude/hooks/planner-review-drafting.sh
```

### P2 — 应急救援 (现在就能干)

**手动 touch 让 stuck sprint 重新进扫描视野** (绕过根因, 临时解阻塞):

```bash
touch ~/.solar/harness/sprints/sprint-20260503-090450.status.json
# 等 12-20s 协调器下个 iter, 应该能看到状态变更并派给 builder pane 1
# 但注意: 此时 100705 还在 planning, 派 090450 会让 builder 排队
```

**警告**: 同时只有 1 个 builder pane (pane 1, glm-5.1), 现在有 100705 在 planning, 090450 / 093223 即使被扫到也得排队. 真要并行需先实现 sprint-20260503-090450 (architect topology) 把 pane 3 用起来 → **递归阻塞**.

---

## 5. 给规划者的建议

1. **不要等 scanner 修好** — 先用 `touch` 救 090450 (架构师拓扑实现), 让 builder 接它. 一旦 architect topology 上线, pane 3 就能并行干 094659 (codex 自测) 或 093223 (codex bridge).
2. **scanner 修复另起一个 sprint** (优先级 P0), 别和 100705/090450 抢 builder.
3. **log 噪音和 hook bug** 可以塞进 scanner 修复 sprint 一起处理 (都在 coordinator 周边).

---

**完成**: 调研报告 195 行 (≤200), 根因 + 时间线 + 3 个修复路径.
**下一步**: 写 sprint-20260503-090450 plan.md (任务 B).
