# Solar 铁律: 状态机优先 (State Machine First)

> **来源: 2026-02-04 监护人亲授的系统架构经验**
> **核心: 复杂任务都是有状态的，用状态机而非端到端穿行**

## 核心洞察

```
世界上绝大部分复杂任务都是有状态的。
要第一时间思考如何将任务拆解为状态接续、传递的不同任务。
通过对比状态正确与否来一步步执行。

监护人的任务从来不是"马上要结果"。
欲速则不达。
```

## 两种模式对比

### ❌ 端到端穿行 (错误)

```
输入 → [步骤1] → [步骤2] → [步骤3] → 输出
         └────────────────────────────┘
              同步执行，一条龙
              中间任何一步错，全部重来
              调试困难，状态丢失
```

**问题:**
- 追求"马上出结果"
- 反复失败，浪费时间和 token
- 难以定位问题在哪一步

### ✅ 状态机 (正确)

```
[步骤1] ──写入──→ [状态A] ──检查──→ [步骤2] ──写入──→ [状态B] ...
                    ↑                              ↑
                  持久化                         持久化
                  可验证                         可验证
                  可恢复                         可恢复
```

**优势:**
- 每步独立，可单独验证
- 状态持久化，断点可恢复
- 异步执行，不阻塞
- 调试清晰，看状态就知道卡在哪

## 实现模式

### 数据库状态表

```sql
CREATE TABLE task_states (
    task_id TEXT PRIMARY KEY,
    task_type TEXT,
    status TEXT,           -- 'pending' → 'step1_done' → 'step2_done' → 'completed'
    current_step TEXT,
    input_data TEXT,       -- JSON
    step_results TEXT,     -- JSON，每步结果
    error TEXT,
    created_at DATETIME,
    updated_at DATETIME
);

-- 状态流转触发器
CREATE TRIGGER tr_task_state_change
AFTER UPDATE ON task_states
WHEN NEW.status != OLD.status
BEGIN
    INSERT INTO task_state_log (task_id, old_status, new_status, changed_at)
    VALUES (NEW.task_id, OLD.status, NEW.status, datetime('now'));
END;
```

### 状态检查器

```bash
# 检查待处理任务
pending=$(sqlite3 $DB "SELECT task_id FROM task_states WHERE status='pending'")

# 处理并更新状态
for task_id in $pending; do
    # 执行步骤
    result=$(process_step "$task_id")

    # 更新状态
    sqlite3 $DB "UPDATE task_states SET status='step1_done', step_results='$result' WHERE task_id='$task_id'"
done
```

## 应用示例

### Mail Agent 重构

**之前 (端到端):**
```bash
while read mail; do
    parse → execute → reply  # 一条龙，任何一步错全部重来
done
```

**之后 (状态机):**
```sql
-- 状态定义
'received' → 'parsed' → 'executing' → 'executed' → 'replied' → 'done'

-- 独立处理器
收件器: 写入 status='received'
解析器: received → parsed
执行器: parsed → executed
回复器: executed → replied
```

### 复杂开发任务

**之前:**
```
设计 → 编码 → 测试 → 部署  # 追求一次性跑通
```

**之后:**
```sql
-- 状态表
design_approved → implementation_done → tests_passed → deployed

-- 每个状态可验证
SELECT * FROM task_states WHERE status='design_approved' AND design_doc IS NOT NULL
```

## 何时使用状态机

| 场景 | 是否用状态机 |
|------|-------------|
| 单步操作 (读文件、简单计算) | ❌ 不需要 |
| 多步骤、可能失败 | ✅ 需要 |
| 需要断点恢复 | ✅ 需要 |
| 异步执行 | ✅ 需要 |
| 需要审计追踪 | ✅ 需要 |
| 监护人的任务 | ✅ 几乎都需要 |

## 检查清单

开始复杂任务前，问自己：

- [ ] 这个任务有几个步骤？
- [ ] 每个步骤可能失败吗？
- [ ] 失败后需要从头来吗？
- [ ] 监护人需要马上看到结果吗？

如果答案是"多步骤、可能失败、需要恢复、不急"→ **用状态机**

## 与其他规则的关系

- **IaST (基础设施即系统表)**: 状态机天然适合用系统表实现
- **任务反思**: 状态机让反思有据可查
- **经济法则**: 状态机减少重复执行，节省 token

## 古语智慧

```
欲速则不达。

追求"马上出结果" → 反复失败 → 浪费更多
接受"状态流转"   → 每步验证 → 实际更快
```

---

*State Machine First Rule v1.0*
*从 2026-02-04 监护人亲授中学到*
*复杂任务都是有状态的*
