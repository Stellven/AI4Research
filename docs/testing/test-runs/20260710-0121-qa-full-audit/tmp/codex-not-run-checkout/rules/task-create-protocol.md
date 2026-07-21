# Solar 铁律: TaskCreate 防颠倒协议

> **解决**: 颠倒问题（顺序错乱、跳步执行、遗漏任务）
> **来源**: 2026-03-27 Solar Hook 升级 P1

## 核心规则

```
接到多步骤任务 → 立即 TaskCreate 拆解 → TaskUpdate 建依赖 → 严格按序执行
```

## 何时必须使用 TaskCreate

| 场景 | 必须? | 原因 |
|------|-------|------|
| 3+ 步骤的任务 | 必须 | 容易跳步或颠倒 |
| 并行子任务 | 必须 | 需要跟踪各自进度 |
| 有依赖关系的任务 | 必须 | blockedBy 强制顺序 |
| 牛马委派 | 必须 | 需要追踪谁在做什么 |
| 单步简单查询 | 不需要 | 过度设计 |
| 与监护人对话 | 不需要 | 直接沟通 |

## 标准流程

### Step 1: 创建任务（全部 pending）

```
TaskCreate(subject="A", description="...")
TaskCreate(subject="B", description="...")
TaskCreate(subject="C", description="...")
```

### Step 2: 建立依赖（TaskUpdate）

```
TaskUpdate(taskId="B", addBlockedBy=["A"])   // B 等 A 完成
TaskUpdate(taskId="C", addBlockedBy=["A"])   // C 也等 A（A→B, A→C 并行）
// 或
TaskUpdate(taskId="C", addBlockedBy=["A","B"]) // C 等 A 和 B 都完成（串行）
```

### Step 3: 按序执行

```
TaskList → 找 blockedBy 为空的 pending 任务 → 开始执行
TaskUpdate(taskId="X", status="in_progress") → 执行 → completed
```

### Step 4: 完成后检查

```
TaskList → 检查是否有新解锁的任务
```

## 依赖模式速查

```
串行:  A → B → C       B.blockedBy=[A], C.blockedBy=[B]
并行:  A → B+C          B.blockedBy=[A], C.blockedBy=[A]
扇出:  A → B,C,D        B.blockedBy=[A], C.blockedBy=[A], D.blockedBy=[A]
汇聚:  B,C → D          D.blockedBy=[B,C]
菱形:  A → B,C → D      B.blockedBy=[A], C.blockedBy=[A], D.blockedBy=[B,C]
```

## API 要点

| 要点 | 说明 |
|------|------|
| blockedBy 只能 TaskUpdate 设置 | 不能在 TaskCreate 时设置 |
| completed 任务不再阻塞 | 已完成的依赖自动解锁下游 |
| blockedBy 是数组 | 支持多对多依赖 |
| ID 格式是字符串 | "1", "2", "3" |

## 禁止

- 禁止: 3+ 步任务不拆直接开干
- 禁止: 跳过 blockedBy 直接执行被阻塞的任务
- 禁止: 只创建任务不更新状态（僵尸任务）
- 禁止: 任务描述为空或过于笼统

## 自检清单

- [ ] 任务拆解了吗？（3+ 步）
- [ ] 依赖关系建了吗？（blockedBy）
- [ ] 执行前查 TaskList 了吗？（确认没有跳步）
- [ ] 完成后更新状态了吗？（避免僵尸）
