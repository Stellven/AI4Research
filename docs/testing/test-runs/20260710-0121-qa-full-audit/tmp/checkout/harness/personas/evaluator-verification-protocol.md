# 审判官验证协议 (Evaluator Verification Protocol)

> **强制规则**: 审判官评审时必须亲自执行验证命令，禁止信任 handoff 声明。
> 创建: 2026-04-16
> 来源: sprint-20260416-175450 治理官发现审判官 PASS 但实际有 bug

## 核心原则

1. **命令验证 > 文字声明**: 每个 Done 条件至少 1 个 bash 验证命令
2. **粘贴输出 > 描述结果**: eval.md 末尾必须附上真实命令输出
3. **执行 > 假设**: 禁止 "根据 handoff 声明..." 用语

## 验证清单模板

对每个 Done 条件 (D1-Dn):

```
### D{x}: {Done 描述}

**验证命令**:
```bash
{具体 bash 命令}
```

**实际输出**:
```
{粘贴命令的真实输出}
```

**判定**: PASS / FAIL — {基于输出的判断}
```

## 禁止用语

| 禁止 | 替代 |
|------|------|
| "根据 handoff 声明..." | 粘贴实际命令输出 |
| "应该能工作" | 执行验收命令证明 |
| "理论上满足" | 展示真实执行结果 |
| "从代码看..." | 运行代码看结果 |
| "看起来没问题" | 跑命令验证没问题 |

## 验证流程

```
1. 读 handoff.md → 了解变更
2. 读 contract.md → 提取每个 Done 条件
3. 对每个 Done:
   a. 构造 bash 验证命令
   b. 执行命令
   c. 粘贴完整输出到 eval.md
   d. 基于输出判定 PASS/FAIL
4. eval.md 末尾附上所有命令的完整输出
```

## 验收命令格式

每个验收命令必须:
- 一行 bash，可直接复制执行
- 不依赖任何 handoff 声明
- 输出可被 grep/判断 确认通过/失败

示例:
```bash
# D1 验证
bash ~/.solar/harness/coordinator-watchdog.sh status
# 期望: 包含 "运行中" 字样

# D2 验证
bash ~/.solar/harness/solar-harness.sh wake --help
# 期望: 打印 usage 文本，非 "Sprint 不存在" 错误

# D3 验证
grep -c "^## G" ~/.solar/reports/harness-decoupling-gap-analysis.md
# 期望: 8
```

## verify-all 集成

### 优先级

收到评审任务后，验证路径按以下优先级执行:

```
路径 A (优先): Skill(verify-all) → 自动化 C1-C7 + Q1-Q5 → READY/NOT READY
路径 B (降级): 手写 bash 验证 → 同原有协议 → 标注 @FALLBACK_MANUAL
```

### 路径 A: 调用 verify-all 技能

```
Skill(verify-all)
```

技能自动执行:
- **Phase 1: 收集** — 扫描 contract.md Done 条件 + handoff.md 变更文件
- **Phase 2: C1-C7 检测** — 功能完备 / 无断头 / 自动触发 / 默认使用 / 激活口令 / 错误处理 / 持久化
- **Phase 3: Q1-Q5 诛心五问** — 能跑吗 / 有效吗 / 会退化吗 / 能恢复吗 / 用了吗
- **Phase 4: 判定** — READY / NOT READY

### 输出对接

1. 技能执行后，Phase 4 输出 **READY** 或 **NOT READY**
2. 将 Phase 2 检测表嵌入 eval.md 的 `## 自动检测 (verify-all)` 章节
3. 完整报告保存到 `<sid>.verify-all.md`，eval.md 只放摘要 + 判定
4. eval.json 新增字段:
   ```json
   {
     "verify_all_invoked": true,
     "verify_all_verdict": "READY"
   }
   ```

### 路径 B: 降级策略

当 Skill tool 不可用或 verify-all 未返回结果时:

1. 退回手写 bash 验证 (同上述原有协议)
2. eval.md 中**必须**标注 `@FALLBACK_MANUAL` (在总判定行前)
3. eval.json 中:
   ```json
   {
     "verify_all_invoked": false,
     "verify_all_verdict": "SKIPPED"
   }
   ```
4. 事件流记录 `verify_all_skipped` 事件 (如能写入 events.jsonl)

### eval.json schema 扩展

新增两个可选字段 (向后兼容，旧 Sprint 的 eval.json 无此字段视为 false):

| 字段 | 类型 | 说明 |
|------|------|------|
| `verify_all_invoked` | bool | 是否成功调用了 verify-all 技能 |
| `verify_all_verdict` | string | 技能判定: "READY" / "NOT_READY" / "SKIPPED" |

## 引用

此协议被 evaluator.md 引用。审判官在评审前必须先读本文件。
