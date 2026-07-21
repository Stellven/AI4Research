# C4 — Autopilot Integration Plan
# TH Social Browser Backend for X · S04 Orchestration-UI

epic_id: `epic-20260525-tech-hotspot-radar-social-browser-backend-for-x-大咖监控`
sprint_id: `sprint-20260525-tech-hotspot-radar-social-browser-backend-for-x-大咖监控-s04-orchestration-ui`
node: `C4`
role: planner
status: spec_only
generated_at: 2026-05-29
knowledge_context: solar-harness context inject used (QMD + Obsidian + Solar DB; mirage:timeout → fallback)
upstream: S02 A1 (7 interfaces + HardBlockerGuard) + S03 C4 (pipeline) + S03 C2 (BrowserLeaseClient + RateLimiter)
hard_blocker: `sprint-20260525-browser-agent-global-operator-cutover` — **autopilot 真执行不得在 blocker PASS 前启动**

> **SPEC-ONLY CAVEAT**: 本文件是 Autopilot Integration 集成规约 (plan only)。  
> 不启动任何 autopilot 实例。真执行在 S05 V1 real e2e 中，且必须等 hard_blocker PASS。

---

## 0. 概览

本节点设计 3 层集成架构（chain-watcher / graph-scheduler / autopilot tick），  
规定 5-phase autopilot 执行流、5 种失败模式 + fallback、以及 HardBlockerGuard 如何  
在 blocker 解除时自动释放 S05 V1 real e2e。

**不包含**: ChatGPT 5.5 high model 调用（本 epic 无此组件）；  
semantic extract 由已有 ThunderOMLX 实例承担（不新起实例，per AC-10 + OQ-02）。

---

## 1. 三层集成架构

### 1.1 Layer 1 — Chain-Watcher (硬阻塞侦测 + 自动解锁)

```
chain-watcher
  监听: sprint-20260525-browser-agent-global-operator-cutover
  目标状态: :passed
  检查间隔: 每 5min (chain-watcher tick, ~/.solar/harness/.chain-watcher.log)
  触发动作: auto-unblock S05 V1 real e2e
```

**触发条件 (HardBlockerGuard)**:
```
HardBlockerGuard.check_blocker(
    sprint_id="sprint-20260525-browser-agent-global-operator-cutover"
) → True   # blocker PASSED → unblock
           # False  # blocker not PASSED → stay blocked
```

当 chain-watcher 侦测到 `browser-agent-global-operator-cutover:passed` 后：
1. 写入 `~/.solar/harness/.chain-watcher.log`：`[AUTO-UNBLOCK] S05-V1-real-e2e unblocked at <ts>`
2. 修改 S05 task_graph：`V1_real_e2e.status = ready`（从 `blocked_by_hard_blocker` 解除）
3. 通知 coordinator pane：`dispatch_ready: sprint-...s05-verification-release V1`

**guard_failure 处理**:
- blocker 未 PASS → chain-watcher 继续轮询，不报错，不强制降级
- chain-watcher 进程宕掉 → 下次 autopilot tick 会重跑 guard check

---

### 1.2 Layer 2 — Graph-Scheduler Dispatch (ready_node 控制)

S05 V1 real e2e 节点在 task_graph 中须携带以下字段：

```json
{
  "id": "V1_real_e2e",
  "required_node_id": "sprint-20260525-browser-agent-global-operator-cutover",
  "required_node_status": "passed",
  "status": "blocked_by_hard_blocker",
  "unblock_via": "chain-watcher"
}
```

graph-scheduler dispatch 逻辑：
```
dag.ready_nodes(graph) →
  skip V1_real_e2e UNLESS required_node_id.status == required_node_status
  skip 任何 required_node_id 未满足的节点
  不报错，静默跳过（标注 skip_reason: hard_blocker_pending）
```

**join gate 规则**:
- S05 整体 join gate 需要 V1_real_e2e 完成（但可先跑 mock-mode V2-V6 验证）
- 若 blocker 长期未 PASS → S05 join gate 挂起，不影响 S04 PASS

---

### 1.3 Layer 3 — Autopilot Tick (分层频率调度)

```
autopilot tick 配置 (spec, 不在本 sprint 启动):

tier1 (P0 大咖 accounts):
  frequency: 每 6h
  max_accounts_per_tick: 由 RateLimiter.global_concurrency=1 决定 (串行)
  cooldown_per_account: 180s (per S02 A1 RateLimiter 5-knob)

tier2 (普通 大咖 accounts):
  frequency: 每 24h
  max_accounts_per_tick: 同上, global_concurrency=1
  cooldown_per_account: 600s

scheduler loop (伪代码, 真实在 S05 执行):
  while autopilot.running:
    tick_start = now()
    ready_accounts = RateLimiter.ready_accounts(tier=tier1)
    for account in ready_accounts[:1]:     # global_concurrency=1
      run_5phase_flow(account)
    sleep_until(tick_start + 6h - elapsed)
```

**模型路由 (per tick)**:
- `ThunderOMLX semantic extract`：复用现有 `~/.thunderomlx/socket` (不新起实例, per AC-10 + OQ-02)
- 无 ChatGPT 5.5 高模型调用 (本 epic 不含此组件)
- 所有 API 调用写入 `model_call_ledger`（3 writes: lease cost / extract cost / fallback cost）

---

## 2. 5-Phase Autopilot Flow

每次 per-account 执行必须顺序经过以下 5 个 phase。  
任一 phase 失败触发对应 failure mode 处理（见第 3 节）。

### Phase 1 — Prep (前置检查)

**目标**: 确认 lease 可用 + HardBlockerGuard 通过，才允许进入 Phase 2。

```
步骤:
  1.1  HardBlockerGuard.check_blocker("browser-agent-global-operator-cutover")
         → False → raise BlockerNotResolved → 全局停止 (不进入 Phase 2)
         → True  → 继续

  1.2  OperatorLeaseManager.is_lease_available()
         → False → failure_mode: lease_fail → Phase 5
         → True  → 继续

  1.3  RateLimiter.check_cooldown(account)
         → cooldown_remaining > 0 → skip account (不算 failure, 正常跳过)
         → 0 → 继续

  1.4  ReadyAccounts.validate(account)
         → account.enabled == False → skip
         → True → 继续
```

**Phase 1 Acceptance**:
- HardBlockerGuard 强制 check，返回 False 必须全局停止
- lease_available 和 cooldown_check 都必须通过才进 Phase 2
- disabled account 直接 skip，不计入 failure

---

### Phase 2 — Trigger (账号激活 + 准备就绪)

**目标**: 从 ready_accounts 队列选取目标账号，完成 rate 校验和 jitter。

```
步骤:
  2.1  ready_accounts = RateLimiter.ready_accounts(tier=account.tier)
         filter: last_scanned_at + cooldown < now()

  2.2  jitter = random.uniform(5, 15)   # ±5..15s per S02 RateLimiter spec
       sleep(jitter)

  2.3  log: "Autopilot trigger: account=@{handle} tier={tier} jitter={jitter}s ts={now}"

  2.4  BackendSelector.pick_backend(accounts=[account], ctx=current_ctx)
         → backend_id = "browser_agent"   (tier1 优先)
         → reason = "tier1_P0_browser_preferred"
```

**Phase 2 Acceptance**:
- jitter 必须在 5..15s 范围，不跳过
- BackendSelector 结果写入日志
- 若 BackendSelector 回退到 rss/manual → 继续但标注 backend_fallback=True

---

### Phase 3 — Call (BrowserLeaseClient 6 ops)

**目标**: 执行真实 browser agent 调用（仅在 hard_blocker PASS 且 mock_mode=0 时）。

```
步骤:
  3.1  lease = BrowserLeaseClient.open(url=f"https://x.com/{account.handle}")
         timeout: 30s
         失败 → failure_mode: lease_fail

  3.2  BrowserLeaseClient.wait(selector="article[data-testid='tweet']", timeout=10s)
         失败 → failure_mode: dom_change

  3.3  BrowserLeaseClient.scroll(direction="down", pages=3)

  3.4  dom_tree = BrowserLeaseClient.dom_extract(selector="article[data-testid='tweet']")
         返回空 → failure_mode: parse_fail

  3.5  screenshot_path = BrowserLeaseClient.screenshot(
           path=f"~/.solar/screenshots/{sprint_id}/{account.handle}-{ts}.png"
       )

  3.6  BrowserLeaseClient.release(lease)
         无论成功失败均必须 release (finally 块保证)
```

**Phase 3 Acceptance**:
- 6 ops 必须按序执行（open→wait→scroll→dom_extract→screenshot→release）
- release 在 finally 块，不允许 lease 泄漏
- mock_mode=1 时所有 6 ops 由 `mock_browser_fixture.py` 代理返回固定 DOM fixture

---

### Phase 4 — Verify (提取 + 去重 + 写库)

**目标**: 解析 DOM，提取 11 字段，去重后写入 social_posts。

```
步骤:
  4.1  post_records = PostExtractor.extract(dom_tree)
         → list[post_record]  (11 字段 per S02 A2)
         空列表 → failure_mode: parse_fail

  4.2  for post in post_records:
         dedup_key = DedupQueue.generate_key(post)    # canonical URL 优先, sha256 fallback
         if DedupQueue.exists(dedup_key, window=24h):
             skip (dedup hit, 不写库)
         else:
             social_posts.insert(post)
             DedupQueue.register(dedup_key)

  4.3  metrics_snapshots.write(account, scan_ts=now, post_count=len(post_records))

  4.4  ThunderOMLX.semantic_extract(post_records)   # 复用现有 socket, 不新起实例
         → social_links + big_name_viewpoints + propagation_chains

  4.5  model_call_ledger.write(
           lease_cost, extract_cost,
           premium_reasoning_cost=0   # 本 epic 不含高模型
       )
```

**Phase 4 Acceptance**:
- 11 字段全部提取（缺字段填 N/A，不允许 None 写库）
- dedup key canonical URL 优先，sha256 fallback（per OQ-04）
- ThunderOMLX 调用不新起实例（per AC-10 + OQ-02）
- model_call_ledger 3 writes 必须执行

---

### Phase 5 — Failure (失败处理 + fallback)

见第 3 节完整 5 failure mode 规范。

**Phase 5 公共规则**:
- 每个 failure mode 必须写入 `scan_state.failure_log`
- per-account 隔离：失败仅影响该账号，batch 继续处理下一个
- StatusSurface.parse_fail_count += 1（触发 parse_fail/dom_change 时）
- StatusSurface.fallback_count += 1（触发 backend fallback 时）
- 不打印 cookie / token / session / auth header

---

## 3. 5 Failure Modes + Fallback Paths

### FM-1: lease_fail

**触发条件**: Phase 1 (`is_lease_available() == False`) 或 Phase 3 (`open()` 超时/异常)

```
检测: OperatorLeaseManager raises OperatorNotReady
      or BrowserLeaseClient.open() timeout > 30s

处理:
  1. log: "lease_fail account=@{handle} ts={now} reason={e}"
  2. StatusSurface.scan_state[account] = "lease_unavail"
  3. 等待: sleep(60s)   # 短暂等待，非 backoff
  4. Retry: OperatorLeaseManager.acquire(retry=1, timeout=10s)
       → 仍失败 → BackendSelector 降级到 rss_public
       → rss_public 不可用 → 降级到 manual_curated
  5. StatusSurface.fallback_count += 1
  6. 继续处理下一 account

Fallback path: browser_agent → rss_public → manual_curated
Kill condition: 连续 3 个 account lease_fail → autopilot pause 1h, alert coordinator
```

---

### FM-2: login_required

**触发条件**: Phase 3 `wait()` 检测到 X 登录墙 selector

```
检测: BrowserLeaseClient.wait(selector="[data-testid='loginButton']", timeout=5s) → found

处理:
  1. log: "login_required account=@{handle} ts={now}"
  2. BrowserLeaseClient.release(lease)   # 立即释放
  3. StatusSurface.scan_state[account] = "login_wall_detected"
  4. alert: 写入 coordinator inbox "login_wall detected @{handle}"
  5. 不重试 (不绕登录, 不尝试绕风控)
  6. 跳过该 account, 继续下一个

Fallback path: 跳过账号 → rss_public fallback for this account
Non-goal assert: 不尝试自动登录；不绕 X 风控；不使用缓存 session

Kill condition: 5 个以上 account 连续 login_required → autopilot pause + alert (可能 IP/session 问题)
```

---

### FM-3: parse_fail

**触发条件**: Phase 3 `dom_extract()` 返回空 或 Phase 4 `PostExtractor.extract()` 返回空

```
检测: dom_tree == [] or len(post_records) == 0

处理:
  1. screenshot_path = BrowserLeaseClient.screenshot(...)   # 截图保留证据
  2. BrowserLeaseClient.release(lease)
  3. log: "parse_fail account=@{handle} ts={now} dom_hash={hash(raw_dom)}"
  4. StatusSurface.parse_fail_count += 1
  5. 若 parse_fail_rate >= 10%: StatusSurface.slo_alert = "parse_fail_rate_red"
  6. Exponential backoff: next_retry = now + min(base=2^attempt * 60s, max=300s)
     (per S02 A1 RateLimiter: base=2, max=300s)
  7. 保存 screenshot path 到 vault (Knowledge/_raw/social/<ts>/<handle>-parse_fail.png)

Fallback path: 等 backoff 后重试最多 3 次；3 次后降级 rss_public
Backoff schedule: 60s → 120s → 300s → 放弃 → rss fallback
```

---

### FM-4: rate_429

**触发条件**: Phase 3 任一 op 返回 HTTP 429 或 X rate limit 标志

```
检测: BrowserLeaseClient 任意 op raises RateLimitError or dom包含 rate_limit_indicator

处理:
  1. BrowserLeaseClient.release(lease)
  2. log: "rate_429 account=@{handle} ts={now}"
  3. per-account backoff (per OQ-06 — per-account 不 global):
       account.backoff_until = now + min(base=2^attempt * 60s, max=300s)
  4. StatusSurface.scan_state[account] = "rate_limited"
  5. 继续处理其他 account (per AC-5 per-account isolation)
  6. 此 account 下次 tick 跳过直到 backoff_until 过期

Fallback path: 等 backoff 到期后自动恢复；不降级 backend（rate_429 是暂时配额，非 backend 不可用）
Kill condition: 5 个以上 account 同时 rate_429 → 全局降频 (tier1 从 6h 延长到 12h) + alert
```

---

### FM-5: dom_change

**触发条件**: Phase 3 `wait()` 超时（selector 未找到）或 dom_extract 结构校验失败

```
检测: BrowserLeaseClient.wait() timeout 或 post_record schema validation error (缺 required field)

处理:
  1. screenshot_path = BrowserLeaseClient.screenshot(...)
  2. BrowserLeaseClient.release(lease)
  3. log: "dom_change account=@{handle} ts={now} selector={selector} error={e}"
  4. StatusSurface.scan_state[account] = "dom_change_detected"
  5. alert: 写入 coordinator inbox "X DOM schema change detected, selector update needed"
  6. 不重试（dom_change 是系统性问题，重试无效）
  7. 保存 screenshot + raw HTML snippet 到 vault 作为诊断证据

Fallback path: 跳过账号 → rss_public fallback
Recovery: 需人工更新 selector spec 后重启 autopilot (自动修复不在本 sprint 范围)

Kill condition: >20% account 触发 dom_change → 全局 autopilot pause + P0 alert
```

---

## 4. HardBlockerGuard 自动解锁规范

```
触发条件:
  chain-watcher 检测到:
    sprint-20260525-browser-agent-global-operator-cutover.status == "passed"

解锁动作序列:
  1. HardBlockerGuard.set_resolved(sprint_id="browser-agent-global-operator-cutover")
  2. 修改 S05 task_graph: V1_real_e2e.status = "ready" (from "blocked_by_hard_blocker")
  3. 修改 S03 mock_mode: BROWSER_AGENT_MOCK_MODE = 0 (实际在 S05 执行时设置)
  4. 写日志: ~/.solar/harness/.chain-watcher.log
     → "[AUTO-UNBLOCK] browser-agent-global-operator-cutover:passed at <ts>"
     → "[AUTO-UNBLOCK] S05 V1_real_e2e: blocked_by_hard_blocker → ready"
  5. 通知 coordinator pane (pane 0): dispatch_ready signal for S05 V1

解锁后 autopilot 启动前检查 (Phase 1 guard, S05 执行时):
  HardBlockerGuard.check_blocker() == True →  allow Phase 2+ 进行
  BROWSER_AGENT_MOCK_MODE 环境变量设为 0   →  BrowserLeaseClient 走真实 lease

不解锁的场景:
  - blocker sprint 仍 in-progress / queued / failed → 继续 mock-mode
  - blocker sprint PASS 但 OperatorLeaseManager.is_lease_available() == False → Phase 1 lease_fail 处理
```

---

## 5. S05 Handoff 启动包

> 本节是给 S05 的集成入口，S04 不执行。

**S05 V1 real e2e 启动条件 (全部满足才可 dispatch)**:
- [ ] `sprint-20260525-browser-agent-global-operator-cutover:passed`
- [ ] `sprint-20260525-tech-hotspot-radar-social-browser-backend-for-x-大咖监控-s03-core-runtime:passed`
- [ ] `sprint-20260525-tech-hotspot-radar-social-browser-backend-for-x-大咖监控-s04-orchestration-ui:passed`
- [ ] `BROWSER_AGENT_MOCK_MODE=0` 已设置
- [ ] autopilot tick 配置已注入 (tier1=6h, tier2=24h, global_concurrency=1)

**S05 需承接的工作**:
1. 真实 BrowserLeaseClient 调用（Phase 3 6 ops，mock-mode=0）
2. 真实 PostExtractor 11 字段提取（Phase 4）
3. 真实 social_posts.insert（Phase 4）
4. 真实 ThunderOMLX semantic extract（Phase 4，复用现有实例）
5. 5 failure mode 真实路径验证（Phase 5）
6. chain-watcher + autopilot tick 真实启动（非 spec）

**不在 S04/S05 范围的内容**:
- ChatGPT 5.5 high model 调用（本 epic 无此组件）
- 新 ThunderOMLX 实例（per AC-10 + OQ-02，只用现有）
- 绕过 HardBlockerGuard 的任何路径

---

## 6. Non-Goals (显式复述 per O10)

1. 不全网爬取（仅 200 账号精确列表）
2. 不绕 X 风控（FM-2 login_required 直接跳过，不尝试绕过）
3. 不绕登录（不缓存 session token，不模拟登录）
4. 不以 X API 为默认（X API 为 optional 最后备选）
5. 不实施 browser operator 本身（仅消费 solar.physical_operator.browser.lease）
6. 不启动第二套 browser system（复用全局 Solar browser operator）
7. 不启动额外 ThunderOMLX 实例（per AC-10 + OQ-02）
8. 不在本 sprint 启动 autopilot（spec only，S05 执行）
9. 不主动 close 父 epic（需 S03+S04+S05+hard_blocker 全部 PASS）
10. 不用乐观词（任何未验证项标 `未验证` 或 `风险`）

---

## 7. Acceptance Checklist

- [x] chain-watcher + graph-scheduler + autopilot tick 3-layer integration documented
- [x] 5-phase autopilot flow (prep/trigger/call/verify/failure) with per-phase acceptance criteria
- [x] 5 failure modes (lease_fail / login_required / parse_fail / rate_429 / dom_change) each with explicit fallback path
- [x] HardBlockerGuard trigger condition explicit: auto-unblock S05 V1 when browser-agent-global-operator-cutover:passed
- [x] NO autopilot started in this sprint; spec only with S05 hand-off documented

---

## 8. Architecture Guard Compliance

- package_boundary: `spec_only` — 本文件仅为规约，不创建可运行代码
- core_hits: none — 不修改主架构主循环
- guard_warnings: none
- guard_errors: none
- write_scope: `docs/social-browser-backend-x/C4-autopilot-integration-plan.md` — 严格遵守

---

Knowledge Context: solar-harness context inject used
Harness Modules Used: harness-knowledge, harness-graph, harness-intent
