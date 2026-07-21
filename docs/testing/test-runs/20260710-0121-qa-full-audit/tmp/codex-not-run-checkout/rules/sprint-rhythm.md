# Solar 铁律: 冲刺节奏控制 (Sprint Rhythm Control)

> **来源: 2026-02-12 监护人亲授**
> **目标: 把成功率拉满，对抗失忆**

## 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    SPRINT RHYTHM CONTROL                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   每个任务 = 20~60 分钟的"冲刺块"                               │
│                                                                 │
│   ┌──────────┐   ┌──────────────────┐   ┌──────────┐           │
│   │ 开场     │ → │ 执行             │ → │ 收尾     │           │
│   │ 30 秒    │   │ 10~40 分钟       │   │ 2 分钟   │           │
│   └──────────┘   └──────────────────┘   └──────────┘           │
│        │                  │                   │                 │
│        ▼                  ▼                   ▼                 │
│   读 STATE.md      只做 Next Actions    写回 Progress          │
│   复述 Mission     不跑题不发散         checkpoint + commit     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 三段式执行 (MUST)

### 1. 开场 (30 秒)

```bash
# 必须执行
cat .solar/STATE.md
```

**输出复述：**
```
【冲刺开始】
Mission: [一句话目标]
Next Actions:
- [ ] Action 1
- [ ] Action 2
```

### 2. 执行 (10-40 分钟)

**铁律：只做 Next Actions 列表里的事**

```
❌ 禁止: 发现新问题就跑去修
❌ 禁止: "顺便优化一下"
❌ 禁止: 超出 Next Actions 范围

✅ 必须: 逐条完成 Next Actions
✅ 必须: 发现新任务 → 记到 LOG/todo.md，不立即做
✅ 必须: 遇到阻塞 → 记到 LOG/errors.md，继续下一条
```

### 3. 收尾 (2 分钟)

```bash
# 更新进度
Edit .solar/STATE.md  # Progress + Next Actions

# 记录命令日志 (可选但推荐)
Edit .solar/LOG/cmd.md

# 提交检查点
git add -A && git commit -m "WIP: [完成了什么]"
```

## LOG 目录结构

```
.solar/
├── STATE.md          # 作战态势 (短期)
├── DECISIONS.md      # 决策日志 (追加式)
└── LOG/              # 事件溯源 (轻量版)
    ├── cmd.md        # 关键命令 + 输出摘要
    ├── bench.md      # 基准数据 (P50/P99/内存/版本)
    ├── errors.md     # 错误码/堆栈/复现步骤
    └── todo.md       # 执行中发现的新任务
```

### LOG/cmd.md 格式

```markdown
## 2026-02-12

### 14:30 - GLM-5 注册
```bash
sqlite3 ~/.solar/solar.db "INSERT INTO collab_model_profiles..."
# ✅ 成功
```

### 14:35 - 小爱配置
```bash
openclaw agent --local --message "测试"
# ❌ Error: Unknown model: zai/glm-5
# 原因: OpenClaw 模型库未收录
```
```

### LOG/bench.md 格式

```markdown
## GLM-5 Benchmark (2026-02-12)

| 指标 | 值 |
|------|-----|
| Model | glm-5 |
| Params | 745B MoE |
| Agentic Coding | 589 |
| Cost/1K | $0.002 |
| Context | 128K |
```

### LOG/errors.md 格式

```markdown
## 2026-02-12

### E001: OpenClaw GLM-5 Not Found
- **错误**: `Unknown model: zai/glm-5`
- **复现**: `openclaw agent --local --message "test"`
- **原因**: OpenClaw 模型库未收录新模型
- **状态**: 等待 OpenClaw 更新
```

## 失忆恢复流程

```
Claude 失忆 / 新会话 / compact 后
              │
              ▼
┌─────────────────────────────────────┐
│ 读 .solar/STATE.md                  │ ← 知道在做什么
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ 读 .solar/LOG/cmd.md (最近10条)     │ ← 知道做过什么
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ 复述 Mission + Next Actions         │ ← 确认理解正确
└────────────────┬────────────────────┘
                 │
                 ▼
           继续冲刺
```

## 冲刺块时长选择

| 任务复杂度 | 冲刺时长 | 说明 |
|-----------|---------|------|
| 简单修复 | 20 分钟 | 单文件改动 |
| 功能实现 | 40 分钟 | 多文件协作 |
| 架构变更 | 60 分钟 | 需要设计+实现 |

**超过 60 分钟 → 必须拆分成多个冲刺块**

## 检查清单

**开场时：**
- [ ] 读了 STATE.md？
- [ ] 复述了 Mission？
- [ ] 明确了 Next Actions？

**执行中：**
- [ ] 只做 Next Actions 里的事？
- [ ] 新发现的任务记到 LOG/todo.md？
- [ ] 错误记到 LOG/errors.md？

**收尾时：**
- [ ] 更新了 Progress？
- [ ] 写了下一步 Next Actions？
- [ ] git commit 了？

## 铁律总结

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   🏃 冲刺节奏控制铁律                                           │
│                                                                 │
│   1. 开场读态势 - 30秒复述 Mission/Next Actions (MUST)          │
│   2. 执行聚焦 - 只做列表里的事，不跑题 (MUST)                   │
│   3. 收尾存档 - 2分钟写回 Progress + checkpoint (MUST)          │
│   4. LOG 溯源 - cmd/bench/errors 三件套 (SHOULD)                │
│                                                                 │
│   哪怕失忆，靠 repo 里的态势板也能"重新上电"                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

*Sprint Rhythm Control v1.0*
*建立于: 2026-02-12*
*监护人亲授: 把成功率拉满*
