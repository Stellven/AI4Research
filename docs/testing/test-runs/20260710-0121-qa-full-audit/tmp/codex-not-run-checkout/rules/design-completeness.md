# Solar 铁律: 设计回答完整性

> **来源**: Meta-Harness Iter 1 — Q5(5/10) + Q3(7/10) 失败分析
> **核心问题**: 设计类回答只给框架不给细节，缺乏可验证性

## 铁律定义

当回答涉及「设计」「规划」「规则定义」时，必须满足：

### 1. 映射表必须完整（不能省略行）
```
❌ 错误: "rule=9, chat=1"（省略了中间类型）
✅ 正确: 完整列出所有类型和对应分值
```

### 2. 阈值必须有依据（不能凭空定）
```
❌ 错误: "≥7.0 → L3"（为什么是7不是6或8？）
❌ 错误: "阈值0.7（经验值）"（"经验值"不是依据）
✅ 正确: "≥7.0 → L3（因为权重0.3×9+0.25×10=5.2，需要4/5维度高分才能到7）"
✅ 正确: "频率阈值30次/分（基于P99延迟≤200ms时最大QPS=45，留35%安全边界→30）"
```

**阈值推导方法（至少用一种）**：
- 数据驱动: P95/P99 统计 + 安全边界
- 成本推导: capacity × (1 - margin) = threshold
- 权重计算: Σ(w_i × d_i) ≥ target → 反推 threshold
- 对比验证: threshold=7时误报率X%，threshold=8时漏报率Y%

### 3. 伪代码必须可执行（不能是描述）
```
❌ 错误: "检查文件大小并输出警告"（描述性）
✅ 正确: "if file_size > threshold: print(warning)"（可执行代码）
```

**伪代码检测模式**：
```
❌ 描述性（必须重写）:
- "检查xxx并输出警告"
- "计算得分"
- "返回结果"
- "遍历列表处理"
- "根据条件判断"

✅ 可执行（合格）:
- if condition: action
- for item in list: process(item)
- score = weight_1 * dim_1 + weight_2 * dim_2
- return {field: value}

判断标准: 把伪代码复制到 Python/JS 解释器，
如果语法正确且逻辑可执行 → 通过
```

**伪代码完整度要求（函数级）**：
```
❌ 片段级（不够）:
- 只有 if 条件，没有外层函数包装
- 只有零散语句，没有输入/输出定义

✅ 函数级（合格）:
- function_name(inputs) → outputs
- 完整的 if/elif/else 覆盖所有分支
- 明确的 return 语句
```

**伪代码语法强制标准 (v1.3 新增)**：
```
伪代码必须放在 ``` 代码块中（不是 JSON 值或行内文字）
必须满足以下 5 项语法要求：

1. 类型化函数签名: function name(param: type, ...) -> return_type
2. 显式变量声明: score = 0, result = [], flag = False
3. 算术/逻辑运算符: +, -, *, /, >, <, ==, and, or（禁止"计算"/"比较"等文字）
4. 控制流标准语法: if/elif/else, for x in y, while cond（禁止"遍历处理"/"根据条件"）
5. 显式 return: return {field: value}（禁止"返回结果"）

违反任何一项 = 描述性伪代码 → 必须重写
```

示例1 — 检测型:
```python
function detect_mock(code: str) -> list[Violation]:
    violations = []
    for line in code.split('\n'):
        if any(kw in line for kw in MOCK_KEYWORDS):
            violations.append(Violation(line_num, 'MOCK_OUTPUT'))
    return violations
```

示例2 — 评分/决策型 (SE-019 模式):
```python
function score_complexity(task: str, context: dict) -> int:
    score = 0
    tokens = len(task.split())
    if tokens > 500: score += 2
    elif tokens > 100: score += 1
    if any(kw in task for kw in ['代码','实现','开发']): score += 2
    if any(kw in task for kw in ['分析','推理','对比']): score += 2
    if context.get('step_count', 0) > 3: score += 2
    if context.get('has_code'): score += 2
    return min(score, 10)
```

示例3 — 状态机/流程型:
```python
function process_task(task: Task) -> Result:
    state = classify(task)  # SIMPLE | MEDIUM | COMPLEX
    if state == 'SIMPLE':
        return delegate(model='glm-4-flash', budget=256)
    elif state == 'MEDIUM':
        return delegate(model='glm-5', budget=2048)
    else:
        return delegate(model='deepseek-r1', budget=4096)
```

### 4. 规则设计必须给正反例
```
❌ 错误: "触发条件：文件处理"（太宽）
✅ 正确:
   触发: Write(file_path, ...) ✅
   触发: Edit(file_path, ...) ✅
   不触发: Grep(pattern, ...) ❌
   不触发: Read(file_path) ❌
```

### 5. 计划必须含验证标准
```
❌ 错误: "阶段一完成后进入阶段二"
✅ 正确: "阶段一验收标准：协议文档通过3个集成测试用例"
```

## 触发条件

当回答包含以下关键词时自动触发：
- 设计/规划/方案/架构
- 规则/流程/机制
- 分类/分层/阈值
- 伪代码/算法

## 预期效果

- Q5 类型题（设计）: 5→8（+3）
- Q3 类型题（规则设计）: 7→9（+2）
- Q2 类型题（规划）: 7.5→9（+1.5）

---

*Design Completeness Protocol v1.3*
*建立于: 2026-04-07*
*更新于: 2026-04-08*
*来源: Meta-Harness Iter-007 — 增加伪代码5项语法强制标准*
