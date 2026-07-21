# Solar Capsule Architecture

> 可验证、可组合、可演进的能力原子

## 1. 核心理念

### 1.1 问题陈述

现有能力系统（Skill/MCP/Agent）存在的问题：

| 问题 | 表现 | 后果 |
|------|------|------|
| 边界模糊 | 不知道会访问什么资源 | 安全风险 |
| 执行不确定 | 不知道是否会完成 | 可靠性差 |
| 责任不清 | 出问题不知道找谁 | 维护困难 |
| 难以组合 | 能力之间不能复用 | 重复开发 |
| 无法验证 | 只能靠测试覆盖 | 潜在Bug |

### 1.2 Capsule 定义

**Capsule（胶囊）是一个自闭环、边界清晰、可形式化验证的能力原子。**

```
Capsule = Specification + Implementation + Verification
        = 规约 + 实现 + 验证
```

核心属性 **SCARE**:
- **S**afety - 安全性可验证
- **C**ompleteness - 完备性可验证
- **A**ccountability - 责任可追溯
- **R**isk - 风险可量化
- **E**volution - 可演进

---

## 2. Capsule 规约 (Specification)

### 2.1 规约结构

```yaml
# capsule.yaml - Capsule 规约文件
apiVersion: capsule/v1
kind: Capsule
metadata:
  name: weather-query
  version: 1.0.0
  namespace: solar.core
  author: Solar
  created: 2026-02-03

# ============================================================
# 接口规约 (Interface Contract)
# ============================================================
interface:
  # 输入规约
  input:
    schema:
      type: object
      properties:
        location:
          type: string
          description: 城市名称
          examples: ["北京", "Shanghai"]
      required: [location]

  # 输出规约
  output:
    schema:
      type: object
      properties:
        success: { type: boolean }
        temperature: { type: string }
        description: { type: string }
      required: [success]

  # 错误规约
  errors:
    - code: LOCATION_NOT_FOUND
      message: 无法找到该城市
      recoverable: true
    - code: API_TIMEOUT
      message: 天气服务超时
      recoverable: true

# ============================================================
# 权限规约 (Permission Contract)
# ============================================================
permissions:
  # 资源访问声明
  resources:
    - type: network
      scope: "https://wttr.in/*"
      operations: [read]

    - type: cache
      scope: "capsule:weather-query:*"
      operations: [read, write]

  # 明确声明不需要的权限
  denies:
    - type: filesystem
    - type: database
    - type: system

# ============================================================
# 保证规约 (Guarantee Contract)
# ============================================================
guarantees:
  # 时间保证
  timing:
    max_duration: 5000ms
    typical_duration: 500ms
    timeout_behavior: return_cached_or_error

  # 幂等性保证
  idempotency: true

  # 副作用声明
  side_effects:
    - type: cache_write
      description: 缓存查询结果
      reversible: true

  # 资源消耗保证
  resource_bounds:
    max_memory: 10MB
    max_cpu_time: 1000ms
    max_network_calls: 3

# ============================================================
# 风险规约 (Risk Contract)
# ============================================================
risks:
  # 成本风险
  cost:
    typical: $0.0001
    max: $0.001
    billing_model: per_call

  # 隐私风险
  privacy:
    data_collected: [location]
    data_retention: none
    third_party_sharing: [wttr.in]

  # 可用性风险
  availability:
    external_dependencies:
      - service: wttr.in
        fallback: cached_data
        sla: best_effort

# ============================================================
# 验证规约 (Verification Contract)
# ============================================================
verification:
  # 前置条件
  preconditions:
    - expr: "input.location.length > 0"
      message: "位置不能为空"
    - expr: "input.location.length < 100"
      message: "位置名称过长"

  # 后置条件
  postconditions:
    - expr: "output.success == true || errors.length > 0"
      message: "必须成功或返回错误"
    - expr: "output.success == true => output.temperature != null"
      message: "成功时必须有温度"

  # 不变量
  invariants:
    - expr: "no_filesystem_access()"
    - expr: "no_database_access()"
    - expr: "network_only(wttr.in)"

  # 测试用例
  test_cases:
    - name: valid_city
      input: { location: "北京" }
      expect: { success: true }

    - name: invalid_city
      input: { location: "不存在的城市12345" }
      expect: { success: false, error: LOCATION_NOT_FOUND }

# ============================================================
# 演进规约 (Evolution Contract)
# ============================================================
evolution:
  # 兼容性
  compatibility:
    backward: true  # 旧调用者可以使用新版本
    forward: false  # 新调用者不能使用旧版本

  # 废弃计划
  deprecation:
    deprecated_features: []
    sunset_date: null
    migration_guide: null

  # 版本约束
  version_constraints:
    min_runtime: "capsule-runtime/1.0"
    dependencies:
      - name: "solar.core.http"
        version: ">=1.0.0"
```

### 2.2 规约类型系统

```typescript
// capsule-types.ts

/**
 * Capsule 接口规约
 */
interface InterfaceContract {
  input: {
    schema: JSONSchema;
    examples?: Record<string, any>[];
  };
  output: {
    schema: JSONSchema;
  };
  errors: ErrorDefinition[];
}

/**
 * 权限规约
 */
interface PermissionContract {
  resources: ResourcePermission[];
  denies: ResourceType[];
}

interface ResourcePermission {
  type: 'network' | 'filesystem' | 'database' | 'cache' | 'system' | 'capsule';
  scope: string;  // glob pattern
  operations: ('read' | 'write' | 'execute' | 'delete')[];
  conditions?: string[];  // 条件表达式
}

/**
 * 保证规约
 */
interface GuaranteeContract {
  timing: {
    max_duration: number;
    typical_duration: number;
    timeout_behavior: 'error' | 'return_cached' | 'return_partial';
  };
  idempotency: boolean;
  side_effects: SideEffect[];
  resource_bounds: ResourceBounds;
}

/**
 * 风险规约
 */
interface RiskContract {
  cost: CostRisk;
  privacy: PrivacyRisk;
  availability: AvailabilityRisk;
}

/**
 * 验证规约
 */
interface VerificationContract {
  preconditions: Condition[];
  postconditions: Condition[];
  invariants: Condition[];
  test_cases: TestCase[];
}

/**
 * 演进规约
 */
interface EvolutionContract {
  compatibility: {
    backward: boolean;
    forward: boolean;
  };
  deprecation: DeprecationInfo;
  version_constraints: VersionConstraints;
}
```

---

## 3. Capsule 协议 (Protocol)

### 3.1 协议层次

```
┌─────────────────────────────────────────────────────────────────┐
│                    CAPSULE PROTOCOL STACK                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Layer 4: Composition Protocol (组合协议)                       │
│           胶囊之间如何组合成更大的能力                          │
│                                                                 │
│  Layer 3: Execution Protocol (执行协议)                         │
│           胶囊如何被调用和执行                                  │
│                                                                 │
│  Layer 2: Verification Protocol (验证协议)                      │
│           胶囊如何被验证和认证                                  │
│                                                                 │
│  Layer 1: Identity Protocol (身份协议)                          │
│           胶囊如何被唯一标识和寻址                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 身份协议 (Identity Protocol)

```
Capsule URI 格式:
  capsule://<namespace>/<name>@<version>[/<instance>]

示例:
  capsule://solar.core/weather-query@1.0.0
  capsule://solar.office/email-search@2.1.0/instance-abc123

命名规则:
  namespace: 反向域名风格 (solar.core, solar.office, user.sihaoli)
  name:      小写字母+连字符 (weather-query, email-search)
  version:   语义化版本 (1.0.0, 2.1.0-beta.1)
```

### 3.3 验证协议 (Verification Protocol)

```yaml
# 验证流程
verification_protocol:
  # Phase 1: 静态验证 (部署前)
  static:
    - schema_validation      # 规约格式正确
    - type_checking          # 类型匹配
    - permission_analysis    # 权限声明完整
    - dependency_resolution  # 依赖可解析

  # Phase 2: 符号验证 (部署前)
  symbolic:
    - precondition_satisfiability   # 前置条件可满足
    - postcondition_reachability    # 后置条件可达
    - invariant_preservation        # 不变量保持
    - termination_analysis          # 终止性分析

  # Phase 3: 运行时验证 (执行时)
  runtime:
    - input_validation       # 输入校验
    - permission_enforcement # 权限强制
    - resource_monitoring    # 资源监控
    - output_validation      # 输出校验

  # Phase 4: 事后验证 (执行后)
  post_execution:
    - postcondition_check    # 后置条件检查
    - side_effect_audit      # 副作用审计
    - cost_accounting        # 成本核算
```

### 3.4 执行协议 (Execution Protocol)

```typescript
/**
 * Capsule 执行协议
 */
interface ExecutionProtocol {
  // 请求格式
  request: {
    capsule_uri: string;       // capsule://solar.core/weather@1.0.0
    input: Record<string, any>;
    context: ExecutionContext;
    options: ExecutionOptions;
  };

  // 响应格式
  response: {
    success: boolean;
    output?: Record<string, any>;
    error?: CapsuleError;
    metadata: ExecutionMetadata;
  };
}

interface ExecutionContext {
  caller: string;              // 调用者身份
  session_id: string;          // 会话ID
  trace_id: string;            // 追踪ID
  permissions: string[];       // 调用者权限
  deadline: number;            // 截止时间
}

interface ExecutionMetadata {
  capsule_uri: string;
  duration_ms: number;
  cost: number;
  resources_used: ResourceUsage;
  verification_result: VerificationResult;
}
```

### 3.5 组合协议 (Composition Protocol)

```yaml
# 组合类型

# 1. 顺序组合 (Sequential)
sequence:
  name: weather-and-notify
  steps:
    - capsule: solar.core/weather-query@1.0.0
      input: { location: "$input.location" }
      output_as: weather_result

    - capsule: solar.core/send-notification@1.0.0
      input:
        title: "天气更新"
        body: "$weather_result.temperature"
      condition: "$weather_result.success"

# 2. 并行组合 (Parallel)
parallel:
  name: multi-city-weather
  branches:
    - capsule: solar.core/weather-query@1.0.0
      input: { location: "北京" }
      output_as: beijing

    - capsule: solar.core/weather-query@1.0.0
      input: { location: "上海" }
      output_as: shanghai

  merge:
    strategy: all  # all | any | majority
    output: { beijing: "$beijing", shanghai: "$shanghai" }

# 3. 条件组合 (Conditional)
conditional:
  name: smart-weather
  condition: "$input.use_cache"
  if_true:
    capsule: solar.core/weather-cache@1.0.0
  if_false:
    capsule: solar.core/weather-query@1.0.0

# 4. 循环组合 (Loop)
loop:
  name: batch-weather
  over: "$input.locations"
  as: location
  capsule: solar.core/weather-query@1.0.0
  input: { location: "$location" }
  collect_as: results

# 5. 错误处理组合 (Fallback)
fallback:
  name: resilient-weather
  primary:
    capsule: solar.core/weather-api@1.0.0
  fallbacks:
    - capsule: solar.core/weather-scrape@1.0.0
      on_error: [API_TIMEOUT, API_ERROR]
    - capsule: solar.core/weather-cache@1.0.0
      on_error: [ANY]
```

### 3.6 组合规约推导

**关键洞察：组合胶囊的规约可以从子胶囊推导**

```
┌─────────────────────────────────────────────────────────────────┐
│              COMPOSITION SPECIFICATION DERIVATION                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  顺序组合 (A → B):                                              │
│  ─────────────────────────────────────────────────────────────  │
│  input(A→B)       = input(A)                                    │
│  output(A→B)      = output(B)                                   │
│  permissions(A→B) = permissions(A) ∪ permissions(B)             │
│  duration(A→B)    = duration(A) + duration(B)                   │
│  cost(A→B)        = cost(A) + cost(B)                           │
│  precond(A→B)     = precond(A)                                  │
│  postcond(A→B)    = postcond(B) ∧ (postcond(A) → precond(B))    │
│                                                                 │
│  并行组合 (A || B):                                             │
│  ─────────────────────────────────────────────────────────────  │
│  input(A||B)      = input(A) ∪ input(B)                         │
│  output(A||B)     = output(A) × output(B)                       │
│  permissions(A||B)= permissions(A) ∪ permissions(B)             │
│  duration(A||B)   = max(duration(A), duration(B))               │
│  cost(A||B)       = cost(A) + cost(B)                           │
│                                                                 │
│  条件组合 (if C then A else B):                                 │
│  ─────────────────────────────────────────────────────────────  │
│  input(C?A:B)     = input(C) ∪ input(A) ∪ input(B)              │
│  output(C?A:B)    = output(A) ∪ output(B)                       │
│  permissions(C?A:B)= permissions(A) ∪ permissions(B)            │
│  duration(C?A:B)  = max(duration(A), duration(B))               │
│  cost(C?A:B)      = max(cost(A), cost(B))                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Capsule 运行时 (Runtime)

### 4.1 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    CAPSULE RUNTIME ARCHITECTURE                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Capsule Registry                      │   │
│  │  (胶囊注册表 - 存储所有已验证胶囊的规约)                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Verification Engine                    │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │   │
│  │  │ Static  │ │Symbolic │ │ Runtime │ │  Post   │       │   │
│  │  │Verifier │ │Verifier │ │ Guard   │ │ Auditor │       │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Execution Sandbox                      │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │   │
│  │  │Resource │ │ Network │ │  Time   │ │  Cost   │       │   │
│  │  │ Limiter │ │ Filter  │ │ Guard   │ │ Meter   │       │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Capsule Executor                       │   │
│  │  (实际执行胶囊代码)                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 执行流程

```
Request → Resolve → Verify → Execute → Audit → Response

┌─────────────────────────────────────────────────────────────────┐
│  1. RESOLVE (解析)                                              │
│     capsule://solar.core/weather@1.0.0                          │
│              ↓                                                  │
│     从 Registry 获取规约                                        │
├─────────────────────────────────────────────────────────────────┤
│  2. VERIFY (验证)                                               │
│     • 输入验证: 符合 input_schema?                              │
│     • 权限验证: 调用者有权限?                                   │
│     • 前置条件: preconditions 满足?                             │
│     • 资源检查: 资源配额足够?                                   │
├─────────────────────────────────────────────────────────────────┤
│  3. EXECUTE (执行)                                              │
│     • 创建隔离沙箱                                              │
│     • 注入允许的资源访问                                        │
│     • 启动计时器和成本计量                                      │
│     • 执行胶囊代码                                              │
│     • 捕获输出和副作用                                          │
├─────────────────────────────────────────────────────────────────┤
│  4. AUDIT (审计)                                                │
│     • 后置条件: postconditions 满足?                            │
│     • 不变量: invariants 保持?                                  │
│     • 副作用: 与声明一致?                                       │
│     • 资源使用: 在 bounds 内?                                   │
├─────────────────────────────────────────────────────────────────┤
│  5. RESPONSE (响应)                                             │
│     • 返回输出                                                  │
│     • 记录执行元数据                                            │
│     • 更新统计信息                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. 与现有系统集成

### 5.1 REE 集成

```
┌─────────────────────────────────────────────────────────────────┐
│                    REE + CAPSULE INTEGRATION                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  优先级更新:                                                    │
│  ─────────────────────────────────────────────────────────────  │
│  P0  Capsule    已验证胶囊 (最高信任)                          │
│  P1  Shortcut   系统快捷指令                                    │
│  P2  Script     脚本缓存                                        │
│  P3  Skill      命令式技能                                      │
│  P4  MCP        外部服务                                        │
│  P5  Agent      多步协作                                        │
│  P6  Code Gen   代码生成                                        │
│                                                                 │
│  转换路径:                                                      │
│  ─────────────────────────────────────────────────────────────  │
│  Skill  → 添加规约 → Capsule                                    │
│  Script → 添加规约 → Capsule                                    │
│  MCP    → 包装规约 → Capsule                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 现有 Skill 迁移

```yaml
# 将现有 weather-fetch 迁移为 Capsule

# Before: skill definition
skill:
  name: weather-fetch
  command: /weather

# After: capsule specification
apiVersion: capsule/v1
kind: Capsule
metadata:
  name: weather-query
  version: 1.0.0
  namespace: solar.core
  migrated_from: skill:weather-fetch

interface:
  input:
    schema:
      type: object
      properties:
        location: { type: string }

  output:
    schema:
      type: object
      properties:
        success: { type: boolean }
        temperature: { type: string }

permissions:
  resources:
    - type: network
      scope: "https://wttr.in/*"
      operations: [read]

guarantees:
  timing:
    max_duration: 5000ms
  idempotency: true
  side_effects: []

verification:
  test_cases:
    - name: beijing
      input: { location: "北京" }
      expect: { success: true }
```

---

## 6. 演进机制

### 6.1 版本演进

```
┌─────────────────────────────────────────────────────────────────┐
│                    CAPSULE VERSION EVOLUTION                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  语义化版本: MAJOR.MINOR.PATCH                                  │
│  ─────────────────────────────────────────────────────────────  │
│  MAJOR: 破坏性变更 (接口不兼容)                                 │
│  MINOR: 新增功能 (向后兼容)                                     │
│  PATCH: Bug修复 (完全兼容)                                      │
│                                                                 │
│  版本约束:                                                      │
│  ─────────────────────────────────────────────────────────────  │
│  ^1.0.0  → >=1.0.0 <2.0.0   (兼容升级)                         │
│  ~1.0.0  → >=1.0.0 <1.1.0   (补丁升级)                         │
│  1.0.0   → =1.0.0           (精确版本)                         │
│                                                                 │
│  演进规则:                                                      │
│  ─────────────────────────────────────────────────────────────  │
│  • 新版本必须通过所有旧版本测试用例                             │
│  • 权限只能收窄不能扩大 (除非 MAJOR)                            │
│  • 时间保证只能缩短不能延长 (除非 MAJOR)                        │
│  • 输出 schema 只能扩展不能删除 (除非 MAJOR)                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 能力增长

```
┌─────────────────────────────────────────────────────────────────┐
│                    CAPABILITY GROWTH MODEL                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 原子胶囊 (Atomic Capsules)                                  │
│     └── 最小能力单元，不可再分                                  │
│         weather-query, send-email, create-file                  │
│                                                                 │
│  2. 组合胶囊 (Composite Capsules)                               │
│     └── 由原子胶囊组合而成                                      │
│         weather-and-notify = weather-query → send-notification  │
│                                                                 │
│  3. 元胶囊 (Meta Capsules)                                      │
│     └── 生成其他胶囊的胶囊                                      │
│         capsule-generator, capsule-migrator                     │
│                                                                 │
│  增长路径:                                                      │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│    需求 → 匹配 → 无匹配? → 生成原子胶囊 → 验证 → 注册           │
│              ↓                   ↓                              │
│           执行              可组合? → 生成组合胶囊              │
│                                  ↓                              │
│                            元模式? → 生成元胶囊                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 数据模型 (IaST)

### 7.1 系统表

```sql
-- Capsule 注册表
CREATE TABLE sys_capsules (
    capsule_id TEXT PRIMARY KEY,        -- capsule://namespace/name@version
    namespace TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,

    -- 规约 (JSON)
    spec_interface JSON,
    spec_permissions JSON,
    spec_guarantees JSON,
    spec_risks JSON,
    spec_verification JSON,
    spec_evolution JSON,

    -- 实现
    implementation_type TEXT,           -- script/skill/mcp/composite
    implementation_ref TEXT,            -- 指向实现

    -- 验证状态
    verification_status TEXT,           -- pending/verified/failed
    verification_report JSON,
    verified_at DATETIME,

    -- 统计
    invoke_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    avg_duration_ms REAL,
    total_cost REAL DEFAULT 0,

    -- 元数据
    author TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(namespace, name, version)
);

-- 组合定义表
CREATE TABLE sys_capsule_compositions (
    composition_id TEXT PRIMARY KEY,
    capsule_id TEXT REFERENCES sys_capsules(capsule_id),
    composition_type TEXT,              -- sequence/parallel/conditional/loop/fallback
    composition_spec JSON,              -- 组合定义
    derived_spec JSON,                  -- 推导出的规约
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 执行日志表
CREATE TABLE sys_capsule_executions (
    execution_id TEXT PRIMARY KEY,
    capsule_id TEXT REFERENCES sys_capsules(capsule_id),
    caller TEXT,
    session_id TEXT,
    trace_id TEXT,

    -- 输入输出
    input JSON,
    output JSON,
    error JSON,

    -- 验证结果
    precondition_result JSON,
    postcondition_result JSON,
    invariant_result JSON,

    -- 资源使用
    duration_ms REAL,
    cost REAL,
    resources_used JSON,

    -- 审计
    side_effects JSON,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 视图: 可用胶囊
CREATE VIEW v_available_capsules AS
SELECT
    c.*,
    CASE
        WHEN c.invoke_count > 0
        THEN c.success_count * 1.0 / c.invoke_count
        ELSE 1.0
    END as success_rate
FROM sys_capsules c
WHERE c.verification_status = 'verified';

-- 视图: 胶囊健康度
CREATE VIEW v_capsule_health AS
SELECT
    capsule_id,
    name,
    invoke_count,
    success_count * 100.0 / NULLIF(invoke_count, 0) as success_rate_pct,
    avg_duration_ms,
    total_cost,
    CASE
        WHEN success_count * 1.0 / NULLIF(invoke_count, 0) < 0.9 THEN 'degraded'
        WHEN avg_duration_ms > json_extract(spec_guarantees, '$.timing.max_duration') THEN 'slow'
        ELSE 'healthy'
    END as health_status
FROM sys_capsules
WHERE invoke_count > 0;
```

---

## 8. 示例

### 8.1 完整示例: Weather Capsule

```yaml
# capsules/solar.core/weather-query/1.0.0/capsule.yaml
apiVersion: capsule/v1
kind: Capsule
metadata:
  name: weather-query
  version: 1.0.0
  namespace: solar.core
  author: Solar

interface:
  input:
    schema:
      type: object
      properties:
        location:
          type: string
          minLength: 1
          maxLength: 100
      required: [location]

  output:
    schema:
      type: object
      properties:
        success: { type: boolean }
        location: { type: string }
        temperature: { type: string }
        feels_like: { type: string }
        humidity: { type: string }
        description: { type: string }
      required: [success]

  errors:
    - code: INVALID_LOCATION
      recoverable: true
    - code: API_ERROR
      recoverable: true

permissions:
  resources:
    - type: network
      scope: "https://wttr.in/*"
      operations: [read]
  denies:
    - type: filesystem
    - type: database

guarantees:
  timing:
    max_duration: 5000ms
    typical_duration: 500ms
    timeout_behavior: error
  idempotency: true
  side_effects: []
  resource_bounds:
    max_memory: 10MB
    max_network_calls: 1

risks:
  cost:
    typical: 0
    max: 0
  privacy:
    data_collected: [location]
    data_retention: none

verification:
  preconditions:
    - expr: "input.location.length > 0"
    - expr: "input.location.length <= 100"
  postconditions:
    - expr: "output.success == true || error != null"
    - expr: "output.success => output.temperature != null"
  test_cases:
    - name: valid_location
      input: { location: "Beijing" }
      assert: { success: true }
    - name: chinese_location
      input: { location: "北京" }
      assert: { success: true }
```

### 8.2 组合示例: Weather Report Capsule

```yaml
# capsules/solar.core/weather-report/1.0.0/capsule.yaml
apiVersion: capsule/v1
kind: Capsule
metadata:
  name: weather-report
  version: 1.0.0
  namespace: solar.core

composition:
  type: sequence
  steps:
    - capsule: solar.core/weather-query@1.0.0
      input: { location: "$input.location" }
      output_as: weather

    - capsule: solar.core/format-message@1.0.0
      input:
        template: "Weather in $weather.location: $weather.temperature, $weather.description"
      output_as: message
      condition: "$weather.success"

    - capsule: solar.core/send-notification@1.0.0
      input:
        title: "Weather Report"
        body: "$message"
      condition: "$input.notify && $weather.success"

# 规约自动从子胶囊推导
# interface, permissions, guarantees, risks 自动计算
```

---

## 9. 下一步

1. **实现 Capsule Runtime** - 核心执行引擎
2. **实现 Verification Engine** - 静态/符号/运行时验证
3. **迁移现有 Skills** - 将 weather-fetch 等迁移为 Capsule
4. **构建 Capsule Registry** - 本地胶囊注册表
5. **实现组合引擎** - 支持组合协议

---

*Capsule Architecture v1.0*
*Solar - 可验证、可组合、可演进的能力原子*
