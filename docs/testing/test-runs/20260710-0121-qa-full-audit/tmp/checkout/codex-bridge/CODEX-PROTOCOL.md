# Solar ↔ Codex 双向协作协议 v2

**日期**: 2026-05-03
**双方**: Codex (独立终端,研究员/监督者) ↔ Solar (规划者+harness 4 pane 系统,执行者)
**目的**: Codex 做深度研究/写合约/监督;Solar 接合约执行 + 接受监督

---

## 1. 角色定位

| 方 | 角色 | 模型 | 职责 |
|----|------|------|------|
| **Codex** | 研究员 + 监督者 | (你的模型) | 深度调研、写 sprint 合约、审查 Solar 的 handoff |
| **Solar** | 规划者 + 执行者 | Opus 4.7 + GLM × 2 + Opus | 接合约 → harness 派 builder 写代码 → evaluator 审 → architect 二审 (opus 拓扑) |

**重点**: Solar 自己不写代码,它**编排** 4 个化身 (planner/builder/evaluator/architect) 干活。Codex 给的合约会被 Solar harness 自动派给 builder。

---

## 2. 文件交换位置 (单一真相源)

```
~/.solar/codex-bridge/
├── from-codex/          ← Codex 写,Solar 读
│   ├── contract-<topic>-<YYYYMMDD-HHMMSS>.md       # 新合约 (Solar 接执行)
│   ├── research-<topic>-<YYYYMMDD-HHMMSS>.md       # 研究报告 (Solar 参考)
│   └── review-<sid>-<YYYYMMDD-HHMMSS>.md           # 监督审查 (Solar 看决定 follow-up)
├── to-codex/            ← Solar 写,Codex 读
│   ├── handoff-<sid>.md                            # Solar 完成的 sprint, 请 codex 审
│   ├── request-research-<topic>.md                 # Solar 需要 codex 做的研究
│   └── inbox.md                                    # 总通知 (Solar 触发什么时贴这里)
└── CODEX-PROTOCOL.md    ← 本文件 (协议规范)
```

**约定**: 双方只通过这两个目录交换文件,不直接调对方进程。

---

## 3. Codex → Solar 流程 (Codex 主动)

### 3.1 写合约让 Solar 执行

Codex 写合约文件,放 `from-codex/contract-<topic>-<timestamp>.md`,格式:

```markdown
---
title: <一句话主题>
priority: low|medium|high
topology: standard | deliberation | research
estimated_hours: 1-4
---

# Sprint Contract — Codex 提交

## Background
<为什么要做,根因/动机>

## Requirements
<要求,500 字以内,具体可执行>

## Definition of Done
- [ ] D1: <条件>
  <!-- verify: cmd="..." expected_exit=0 output_pattern="..." -->
- [ ] D2: <条件>
  <!-- verify: cmd="..." expected_exit=0 output_pattern="..." -->
- [ ] D3: <条件>
  <!-- verify: cmd="..." expected_exit=0 output_pattern="..." -->

## Constraints
- 不破坏现有 API
- 修改范围限于 <path1> <path2>
- 不改 Sprint 历史文件
- 凭据从 ~/.solar/secrets/ 读, 不入版本控制

## Out of Scope
- <不做啥>
```

**Solar 接收方式**:
- chain-watcher v3 (后台守护) 每 30s 扫 `from-codex/` 所有 `.md` 文件 (排除 `*.template.md` 和 `.processed/`)
- 按 filename prefix 分发:
  - `contract-*` / `execution-contract-*` → 自动起 sprint
  - `review-*` → 写 PLANNER-INBOX 通知 + pane 0 (planner) send-keys
  - `research-*` → 同 review, 写 PLANNER-INBOX + pane 0 通知
  - 其它 `.md` → 通知 planner 处理
- 已处理文件移入 `.processed/` 目录去重
- 每轮扫描结束输出统计 log (contracts/reviews/research/unknown)

**topology 字段**:
- `standard`: builder (glm) → evaluator (glm) → passed (省钱)
- `deliberation`: builder → evaluator → architect (opus) 二审 → passed (烧 max 月费)
- `research`: 直接 architect (opus) 干,跳过 builder

### 3.2 写研究报告供 Solar 参考

Codex 主动调研后,写 `from-codex/research-<topic>-<timestamp>.md`:

```markdown
# Research: <topic>

**时间**: <ISO8601>
**深度**: light | deep
**结论**: <一句话>

## 关键发现
- ...

## 推荐 Solar 做的下一步
- 建议起 sprint: <主题>
- 或者: 直接 follow-up 现有 sprint <sid>
```

Solar 看到 → 决定起 sprint 或 ignore。

### 3.3 审查 Solar 完成的 sprint

Codex 看 `to-codex/handoff-<sid>.md` 后,写 `from-codex/review-<sid>-<timestamp>.md`:

```markdown
# Codex Review: sprint-<sid>

## 总判定: APPROVE | NEEDS_FOLLOW_UP | REJECT

## 已通过的
- D1 ✓ ...

## 设计层缺陷 (Solar 没看到的)
- <缺陷>

## 建议 follow-up sprint
- <主题 + Done 草案>
```

Solar 看到 NEEDS_FOLLOW_UP → 起 follow-up sprint。

---

## 4. Solar → Codex 流程 (Solar 触发)

### 4.1 sprint PASS 后请求 codex 审 (deliberation 拓扑)

Solar 完成 sprint 后,把 handoff + eval 复制到 `to-codex/handoff-<sid>.md`:

```markdown
# Sprint Handoff for Codex Review

**sprint_id**: <sid>
**evaluator verdict**: PASS
**rounds**: <N>

## 链接
- 合约: ~/.solar/harness/sprints/<sid>.contract.md
- 实施: ~/.solar/harness/sprints/<sid>.handoff.md
- 评审: ~/.solar/harness/sprints/<sid>.eval.md

## 摘要
<Solar 提取的关键改动>

## 请 Codex 审的点
- [ ] 设计层是否有 Solar 没看到的缺陷?
- [ ] 跟 v2 蓝图方向是否一致?
- [ ] 是否需要 follow-up?
```

### 4.2 Solar 请求 codex 调研

Solar 遇到不确定的方向,写 `to-codex/request-research-<topic>.md`:

```markdown
# Research Request

**topic**: <主题>
**urgency**: low|medium|high
**context**: <为什么要研究>

## 需要 codex 回答的问题
1. ...
2. ...

## 可参考资料
- <文件路径>
```

Codex 看到 → 调研 → 写 `from-codex/research-*.md`。

---

## 5. 第一个测试任务 (给 codex 开工)

**topic**: `validate-codex-bridge`
**目的**: 验证双向协议可用,作为 codex 入门

### 任务 (3 步)

1. 读这份协议
2. 写一份 `from-codex/research-validate-codex-bridge-<timestamp>.md`,内容:
   - codex 自己的模型 + 上下文容量
   - 你能做什么类型的任务最擅长 (long-context 调研?数学推理?代码审查?)
   - 你**不擅长**什么
   - 建议 Solar 怎么用你 (哪些任务给你做最值)
3. 写一份 `from-codex/contract-codex-self-test-<timestamp>.md`,起一个**最小验证 sprint**,要求 Solar 把它跑通,验证 chain 工作

Solar 看到 → 用 solar-harness 把它转成 sprint → builder 干 → evaluator 审 → 你监督 → 闭环。

---

## 6. Solar 已搭好的设施

- ✅ harness 4 pane 全跑通 (planner/builder/evaluator/architect)
- ✅ chain-watcher v3 后台守护 (全文件扫描 + 按 prefix 分发 + pane 0 通知 + PID file mkdir 锁防多开)
- ✅ control-plane.sh 正式运维入口 (Phase A read-only: help/status 子命令)
- ✅ lib/run-state.sh 统一 state helper (rs_transition/rs_read_status 等函数库)
- ✅ secrets 安全 (~/.solar/secrets/zhipu.env)
- ✅ evaluator 实测铁律 (NEW 文件必 ls / verify 输出非空)
- ✅ architect (opus) 待命 pane 0.3 (deliberation/research 拓扑用)
- ✅ PID file 锁 (chain-watcher 用 `mkdir` 原子锁, macOS 兼容, 非 flock)
- ✅ pane 0 send-keys 通知 (chain-watcher 检测新文件后直接写 planner pane input, 不等 planner 自己 watch)

## 7. 已知风险 (codex 注意)

- Solar 改协调器代码常引入新副作用 (今天事故 5+ 次), 请 codex 审协调器改动时**慢一拍 + 找副作用**
- evaluator 之前有 2 次放水 (信 handoff 文字),实测铁律加了但仍可能漏 — codex 监督是第二道防线
- chain-watcher 起 sprint 默认按 mtime,可能跟你期望优先级不符 → 你可在合约 frontmatter 加 `priority` 字段,Solar 会按 priority 调整

---

## 8. 通信节奏

- Codex 写合约后,**不需要通知 Solar** — chain-watcher 30s 内扫到
- Solar 完成 sprint 后,会主动写 `to-codex/handoff-<sid>.md` + 在 `to-codex/inbox.md` 追加一行
- 如有紧急,双方在 `to-codex/inbox.md` / `from-codex/inbox.md` 用 `[URGENT]` 前缀

---

**协议生效**: 即时
**版本**: v2
**修订**: 任何一方发现协议不工作,改本文件 + 通知对方
