# A1 — Control Plane / Data Plane / Interfaces

sprint_id: `sprint-20260525-tech-hotspot-radar-social-browser-backend-for-x-大咖监控-s02-architecture`
node: `A1`
package_boundary: `spec_only` (no code change; browser_agent not invoked — hard blocker active)
generated_at: `2026-05-28`
status: `reviewing`

> 本文件是 **架构契约 (spec)**，不执行任何 CLI、不申请任何 browser lease、不调用 X API、不跑 SQL。
> 所有接口签名是 S03 实现的契约面，所有数值是 S03 的默认参数来源。
> Hard blocker 未解除前，任何实现节点不得起飞 (见 §6 HardBlockerGuard)。

---

## §0 设计输入与回链

| 输入 | 来源 | 用途 |
|------|------|------|
| O1/O2/O3 backend + operator + ratelimit 契约 | `s01-requirements.requirements.backend_operator_ratelimit.md` | §1 BackendSelector + §2 RateLimiter + §4.1 BrowserLeaseClient |
| O4/O5/O6 extraction + dedup + downstream 契约 | `s01-requirements.requirements.extraction_dedup_downstream.md` | §3 数据平面 10 步 + §4.2 PostExtractor 11 字段 |
| O7/O8/O9 CLI + WebUI + blocker 契约 | `s01-requirements.requirements.cli_webui_blocker.md` | §4.5 CLI + §4.6 StatusSurface + §6 HardBlockerGuard |
| PRD 全文 | `s02-architecture.prd.md` | 全局约束 (no scraping / no bypass / no duplicate browser) |
| task_graph A1 acceptance A-A1-1..6 | `s02-architecture.task_graph.json` | §7 验收映射 |

requirement_ids covered: `O1, O2, O3, O6, O7, O8, O9`
acceptance_ids covered: `A-A1-1, A-A1-2, A-A1-3, A-A1-4, A-A1-5, A-A1-6`

---

## §1 控制平面 — BackendSelector (4-tier fallback)  → A-A1-1

### §1.1 固定 4 级降级链 (顺序锁定，不得调换)

| tier | backend_id | 触发条件 | 不可用时动作 |
|------|-----------|---------|------------|
| 1 | `browser_agent` | `operator_ready()` == true 且 lease 可申请 | 降级 tier 2 |
| 2 | `rss_public` | `rss_seed_available()` == true | 降级 tier 3 |
| 3 | `manual_curated` | 永远可用 (no-op 后端) | 终点；warn + posts=0 |
| 4 | `x_api_optional` | **仅** 用户显式 `--backend x_api` + token + `--ack-x-api-cost` | 不参与 auto 链 |

> 关键不变量 (来自 O1 AC-O1-2 + N3 AC-O7-2-c)：**`auto` 模式永不回落到 `x_api`**。
> x_api 是第 4 级 *optional* 后端，只能被显式选择，不能被 selector 自动选中。

### §1.2 selector 签名 (A-A1-1 锁定)

```python
def pick_backend(accounts: list[Account], ctx: SelectionContext) -> tuple[str, str]:
    """
    Return (backend_id, reason).
    backend_id ∈ {"browser_agent", "rss_public", "manual_curated", "x_api_optional"}
    Never returns "x_api_optional" unless ctx.user_arg == "x_api".
    reason 是机器可读短码，写入 scan job 与 StatusSurface.fallback。
    """
```

`SelectionContext` 字段契约：

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_arg` | str | `{auto, browser, rss, manual, x_api}`，默认 `auto` |
| `operator_ready` | callable -> bool | tier1 探针 (N3 AC-O8-2，lease 申请并立即释放) |
| `rss_seed_available` | callable -> bool | tier2 探针 |
| `x_api_token_present` | bool | env `SOLAR_HOTSPOT_X_API_TOKEN` 非空 |
| `x_api_cost_acked` | bool | `--ack-x-api-cost` flag |
| `hard_blocker_resolved` | bool | §6 HardBlockerGuard 结果 |

### §1.3 决策序 (伪代码，契约非实现)

```
if user_arg == "x_api":
    if not (x_api_token_present and x_api_cost_acked):
        raise CLIRejection("x_api requires token + --ack-x-api-cost")
    return ("x_api_optional", "explicit_user_choice_x_api")
if user_arg != "auto":
    return (map_arg_to_backend(user_arg), f"explicit_user_choice_{user_arg}")
# auto path — x_api 不可达
if not hard_blocker_resolved:
    # tier1 在 blocker 未解时直接不可用 → 走 tier2/tier3 (见 OQ-01 in A4)
    pass
if operator_ready():
    return ("browser_agent", "operator_ready")
if rss_seed_available():
    return ("rss_public", "browser_not_ready_fallback_rss")
return ("manual_curated", "browser_and_rss_unavailable_warn_only")
```

`reason` 短码枚举 (写入观测)：`operator_ready`, `browser_not_ready_fallback_rss`,
`browser_and_rss_unavailable_warn_only`, `explicit_user_choice_<backend>`,
`explicit_user_choice_x_api`, `blocked_tier1_skipped`.

### §1.4 OperatorLeaseManager (via solar.physical_operator.browser.lease)

BackendSelector tier1 不直接持有 browser；它通过 `OperatorLeaseManager` 申请全局物理算子
lease (O2 AC-O2-2 禁止自建常驻 Playwright/Chrome)。

```python
class OperatorLeaseManager:
    operator_id = "solar.physical_operator.browser.lease"
    def probe(self) -> ProbeResult: ...   # operator_ready 探针；不持有 lease
    def acquire(self, ctx: LeaseContext) -> LeaseHandle: ...  # 申请；可 raise LeaseUnavailable
    def release(self, handle: LeaseHandle) -> None: ...        # 必须在 finally 中调用
```

- `probe()` 返回 `{ready, last_check_at, reason_if_not_ready}`，reason_if_not_ready 取值
  `OPERATOR_NOT_DEPLOYED / LEASE_TIMEOUT / LEASE_REJECTED / PROBE_EXCEPTION` (N3 AC-O8-2)。
- `acquire()` 失败 = browser 后端不可用 = 触发 §1.1 tier1→tier2 降级 (O2 AC-O2-3)。
- 不维护 browser 进程池；每次采集 acquire→use→release 一个 lease。

---

## §2 控制平面 — RateLimiter (5 knobs)  → A-A1-2

5 个速率旋钮 (来源 O3 AC-O3-1..5)，全部参数化，默认值在此锁定，可由环境变量门覆盖：

| # | knob | 默认 | 覆盖门 (env) | 语义 / 回链 |
|---|------|------|------------|-----------|
| 1 | `per_account_cooldown` | tier1=**180s** / tier2=**600s** | `SOLAR_HOTSPOT_SOCIAL_COOLDOWN_T1/T2` | 同账号两次扫描最小间隔 (O3 AC-O3-1) |
| 2 | `global_concurrency` | **1** | `SOLAR_HOTSPOT_SOCIAL_BROWSER_MAX_CONCURRENCY` | 同时仅 1 个 lease 扫描 (O3 AC-O3-2，CLI 不暴露以防误开) |
| 3 | `jitter` | **+5..15s** 随机 | `SOLAR_HOTSPOT_SOCIAL_JITTER_MIN/MAX` | 请求间随机抖动 (O3 AC-O3-3) |
| 4 | `exp_backoff` | base=**2** / max=**300s** / initial=**5s** | `..._BACKOFF_BASE/MAX/INITIAL` | login/rate/parse 失败退避 (O3 AC-O3-4) |
| 5 | `tier_scan_frequency` | tier1=**6h** / tier2=**24h** | `..._SCAN_FREQ_T1/T2` | tier1/tier2 频率分离 (O3 AC-O3-5) |

签名契约：

```python
class RateLimiter:
    def __init__(self, knobs: RateKnobs): ...
    def cooldown_remaining(self, handle: str, tier: str) -> float:  # 秒；>0 表示仍在冷却
        ...
    def next_jitter_delay(self) -> float: ...                       # uniform(jitter_min, jitter_max)
    def backoff_delay(self, attempt: int) -> float:                # min(initial * base**attempt, max)
        ...
    def should_scan(self, handle: str, tier: str, now: float) -> bool:  # cooldown + tier freq 联合
        ...
    def acquire_global_slot(self) -> bool:                          # concurrency 闸 (默认 1)
        ...
```

约束：
- `per_account_cooldown` 下限硬性 ≥60s (N3 AC-O7-4)；CLI `--cooldown-seconds` 不得设低于此。
- `global_concurrency` 默认 1，不通过 CLI flag 暴露，仅 env 门可调 (N3 AC-O7-4)。
- backoff/jitter 参数仅 env 门，不进 CLI flag (避免误用)。
- backoff 上界 300s 后不再无限重试 → 转 §5 failure mode 记录 + cooldown 该账号。

---

## §3 数据平面 — 10 步流水线  → A-A1-3

入口 `collect-social`，终点 `model_call_ledger` (3 写)。每步带失败标记
`pipeline_status='failed_at_step_<N>'`，单步失败不阻塞同批其余 post (O6 AC-O6-10)。

```
collect-social --backend <b>
   │
   ▼  pick_backend(accounts, ctx) → (backend_id, reason)         [控制平面]
   ▼  OperatorLeaseManager.acquire()  (tier1 path)
   │
[1] BrowserLeaseClient: open→wait→scroll→dom_extract→(screenshot)→close   (6 ops)
        输出: 可见 post 容器集合 (raw DOM)
[2] PostExtractor: DOM → 11 字段 post_record (含 raw_dom_hash, screenshot_path)
[3] DedupQueue (24h): compute_dedup_key → 命中则 skip + 写 dedup_hit 观测行
        miss → INSERT social_posts (ON CONFLICT(dedup_key) DO NOTHING)
[4] metrics snapshot → social_post_snapshots (metrics 时序，不复写主行)
[5] semantic extract → ThunderOMLX/Qwen3.6 (复用既有实例, 零新增进程)
        → social_semantic_extracts        【ledger write #1: local semantic】
[6] social_links: links_github/arxiv/youtube → social_links (source_post_id 反向引用)
[7] big_name_viewpoints + propagation_chains: viewpoint 聚合 + 跨 200 seed 传播链
        (若 viewpoint 升级 premium reasoning) 【ledger write #2: premium reasoning】
[8] downstream dispatch: links_* → 既有 GitHub/YouTube/paper dispatcher (零新增 dispatcher)
[9] Knowledge/_raw/social/<yyyy-mm-dd>/<handle>/<post_id_or_hash>.md → ingest queue
[10] AI Influence report 聚合 → 写 collection_backend 占比
        【ledger write #3: report 聚合调用账本 flush】
   │
   ▼  OperatorLeaseManager.release()  (finally, 无论成败)
```

### §3.1 model_call_ledger 3 写明示 (A-A1-3 关键)

| ledger write | 触发步骤 | origin | model | source_table |
|--------------|---------|--------|-------|--------------|
| #1 local semantic | [5] | `browser_agent_social_pipeline` | `qwen3.6` / `thunderomlx-*` | `social_semantic_extracts` |
| #2 premium reasoning | [7] (条件升级) | `browser_agent_social_pipeline` | `premium-<vendor>-<name>` | `big_name_viewpoints` |
| #3 report aggregate flush | [10] | `browser_agent_social_pipeline` | 聚合统计 (token usage rollup) | report 产物 |

每条 ledger 行必填 `provider, model, prompt_token_count, completion_token_count, cost_usd,
origin, source_table, source_row_id` (O6 AC-O6-9 + §4.4)。

### §3.2 步间数据契约 (IO 表)

| 步 | 输入 | 输出 | dedup 守卫 |
|----|------|------|-----------|
| 1 | lease + handle | raw DOM 容器 | — |
| 2 | raw DOM | 11 字段 post_record | — |
| 3 | post_record | social_posts (UNIQUE dedup_key) | **前置 dedup，写库前判定** |
| 4 | social_posts | social_post_snapshots | metrics 不复写主行 |
| 5 | social_posts.text | social_semantic_extracts | dedup key 过滤 |
| 6 | social_posts.links_* | social_links | — |
| 7 | semantic extracts | big_name_viewpoints + propagation_chains | viewpoint 按 dedup key 去重 |
| 8 | social_links | dispatcher CLI job_id | — |
| 9 | social_posts 整条 | Knowledge raw md + ingest_id | raw 数 ≥ social_posts 行数 |
| 10 | viewpoints + chains | AI Influence report | backend 占比可见 |

---

## §4 七大接口签名  → A-A1-4

### §4.1 接口① BrowserLeaseClient (6 methods, 对应 O2 6 capabilities)

```python
class BrowserLeaseClient:
    def open_url(self, url: str) -> None: ...                 # 1. open https://x.com/<handle>
    def wait_for_content(self, timeout_s: float) -> bool: ... # 2. 等待内容/登录态
    def controlled_scroll(self, rounds: int) -> None: ...     # 3. 小范围受控滚动 (≤max_scroll_rounds)
    def dom_extract(self) -> list[RawPostNode]: ...           # 4. 可见 DOM 抽取
    def screenshot_fallback(self, reason: str) -> str: ...    # 5. 解析失败截图 → path
    def close_release_lease(self) -> None: ...                # 6. 关闭并释放 lease
```

acceptance：6 方法一一对应 O2 6 capabilities；无第 7 方法绕过 lease；
`controlled_scroll` rounds ≤ `--max-scroll-rounds` (1–10, 默认 3)；
`screenshot_fallback` 返回路径写入 post_record.screenshot_path (见 §4.2 字段 #9)。

### §4.2 接口② PostExtractor (11 字段族)

输出 `post_record` (O4 11 字段族)：

| # | 字段 | 类型 | 必填 | 备注 |
|---|------|------|------|------|
| 1 | `post_id` | TEXT | 否 | 不可见记 NULL，依赖 post_url 唯一 |
| 2 | `author_handle` | TEXT | 是 | 去 `@`，小写 |
| 3 | `text` | TEXT | 是 | UTF-8 保留换行 |
| 4 | `created_at` / `visible_relative_time` | TEXT | 是 | 优先 ISO，fallback 相对时间 |
| 5 | `post_url` | TEXT | 是 | canonical `https://x.com/<h>/status/<id>` |
| 6 | `metrics_{reply,repost,like,view}` | INT 或 `'N/A'` | 否 | 不可见写 `'N/A'`，不写 0 |
| 7 | `urls` + `links_{github,arxiv,youtube}` | JSON array | 否 | 缺省 `[]` 非 NULL |
| 8 | `raw_dom_hash` | TEXT sha256 | 是 | DOM 变更检测 |
| 9 | `screenshot_path` | TEXT/NULL | 否 | 解析成功 NULL；失败非空 |
| 10 | `collection_backend` | TEXT | 是 | 常量 `'browser_agent'` |
| 11 | `collected_at` | TEXT ISO UTC | 是 | lease 释放前写入 |

acceptance：11 字段族齐全；解析失败 → screenshot_path + raw_dom_hash 双非空，不丢 post
(O4 AC-O4-3)；metrics 不可见 `'N/A'` 而非 0 (O4 AC-O4-4)。

### §4.3 接口③ BackendSelector

签名见 §1.2 `pick_backend(accounts, ctx) -> (backend_id, reason)`。
acceptance：4-tier 顺序锁定；auto 永不返回 x_api_optional；reason 短码可观测。

### §4.4 接口④ RateLimiter

签名见 §2 (`cooldown_remaining / next_jitter_delay / backoff_delay / should_scan /
acquire_global_slot`)。acceptance：5 knobs 参数化，concurrency 默认 1，cooldown ≥60s。

### §4.5 接口⑤ CLI subcommand + exit codes

```text
scripts/tech_hotspot_radar.py collect-social \
    --backend {browser,auto,rss,manual,x_api}   # 默认 auto
    --limit-accounts N                           # ≥1, ≤ enabled accounts
    [--tier {tier1,tier2,all}]                   # 默认 all
    [--dry-run]                                  # 仅列计划不访问 x.com
    [--cooldown-seconds SEC]                     # ≥60
    [--max-scroll-rounds R]                      # 1-10
    [--ack-x-api-cost]                           # 仅 --backend x_api 必填
```

exit code 契约：

| rc | 条件 |
|----|------|
| 0 | 正常 (含 auto→manual no-op；stdout 含 `WARN` + fallback 原因) |
| 2 | 参数错误 (limit-accounts 越界 / backend 非法值) |
| 3 | x_api 缺 token 或缺 `--ack-x-api-cost` (拒绝静默 fallback) |
| 4 | hard blocker 未解除且请求 `--backend browser` (见 §6) |

acceptance：复用既有 `collect-social` 子命令 (OQ-N3-01 候选 A，A4 决议)；
auto 链不含 x_api；x_api 三条件 (token + flag + ack) 缺一 rc=3。
**入口位置最终选型 (cmd_collect_social 扩展 vs 新子命令) 留 A4 OQ / S03 落地。**

### §4.6 接口⑥ StatusSurface (7 indicators)

JSON payload `schema_version = solar.social_browser_backend.status.v1` (N3 §4.3)：

| # | indicator | 类型 | 数据源 |
|---|-----------|------|--------|
| 1 | `accounts{total,enabled,scanned_today}` | INT×3 | social_accounts + social_posts |
| 2 | `browser_backend_ready{ready,last_check_at,reason_if_not_ready}` | obj | operator_ready 探针 |
| 3 | `scan{pending,running,failed_today}` | INT×3 | scan job 队列 |
| 4 | `last_scan_time` | TEXT | `MAX(collected_at)`；空时 `"never"` |
| 5 | `parse_failure_count_today` | INT | `screenshot_path IS NOT NULL` 当日计数 |
| 6 | `fallback_count_today` | INT | backend=manual 或 fallback_from!=NULL |
| 7 | `posts_collected_by_backend` | JSON obj | `GROUP BY collection_backend` |

acceptance：7 指标族契约名固定；数据源不可达显 `"no data yet"` 非 0/NULL (N3 AC-O8-3)；
字段变更 bump schema_version (N3 AC-O8-4)。

### §4.7 接口⑦ HardBlockerGuard

详见 §6。签名 `assert_unblocked()`，未解除 `raise BlockerNotResolved`。

---

## §5 五种失败模式 + 观测钩子  → A-A1-5

| # | failure mode | 检测点 | 处置 | 观测钩子 |
|---|-------------|-------|------|---------|
| 1 | `lease_fail` | `OperatorLeaseManager.acquire()` raise | tier1→tier2 降级 (§1.1) | StatusSurface #2 `browser_backend_ready.reason_if_not_ready=LEASE_*`；scan reason=`browser_not_ready_fallback_rss` |
| 2 | `login_required` | `wait_for_content` 返回登录墙 | **立即停止**，标 cooldown，记录；**不绕过** (O3 AC-O3-7) | scan job `pipeline_status=failed_at_step_1`；session event `social_login_required` |
| 3 | `parse_fail` | `dom_extract` 产物为空/异常 | `screenshot_fallback` 保底，写 screenshot_path + raw_dom_hash，post 不丢 (O4 AC-O4-3) | StatusSurface #5 `parse_failure_count_today` +1 (>0 黄 / >10 红) |
| 4 | `rate_429` | HTTP/UI 限速信号 | `RateLimiter.backoff_delay` 指数退避；**per-account** 非全局 (A4 OQ-06) | session event `social_rate_429`；该账号 cooldown 延长 |
| 5 | `dom_change` | `raw_dom_hash` 与历史不符 / selector miss | selector abstraction fallback + screenshot；同 dedup key 则 UPDATE 不 INSERT (O5 AC-O5-4) | `raw_dom_hash` diff 记 social_post_snapshots；parse_failure 计数联动 |

通用红线 (PRD + O3 AC-O3-6/7)：检测到 CAPTCHA / rate limit page / login redirect →
立即停止当前采集 + 标 cooldown + 记录原因 + **不尝试绕过/重试受限访问**。

---

## §6 HardBlockerGuard 强制闸  → A-A1-6

### §6.1 闸契约

```python
class HardBlockerGuard:
    BLOCKER_SPRINT = "sprint-20260525-browser-agent-global-operator-cutover"
    REQUIRED_STATUS = "passed"   # blocker sprint 所有 outcome 节点 + parent status 均 passed

    def assert_unblocked(self) -> None:
        if not self._blocker_passed():
            raise BlockerNotResolved(
                f"{self.BLOCKER_SPRINT}:{self.REQUIRED_STATUS} not met; "
                "browser_agent backend dispatch refused"
            )
```

### §6.2 强制检查时机

- **sprint dispatch 时** (coordinator 派 builder 前)：blocker active → reject dispatch +
  写 session event `dispatch_blocked_by_upstream` (N3 AC-O9-2)。
- **CLI `--backend browser` 时**：`assert_unblocked()` 失败 → CLI rc=4 (§4.5)。
- **BackendSelector auto path**：blocker 未解 → tier1 skip (reason=`blocked_tier1_skipped`)，
  直接评估 tier2/tier3 (与 A4 OQ-01 immediate rss fallback 对齐)。

### §6.3 解除条件 (N3 AC-O9-3)

blocker 解除 = blocker sprint task_graph 全 outcome `status='passed'` AND parent
`status.json.status='passed'`。状态机自动 `blocked→queued`；不允许人工 unblock 绕过验收。

### §6.4 blocked 记录 (N3 AC-O9-1)

`<sid>.status.json` 必含 `status=blocked` + `blocked.{reason, blocker_sprint_id,
blocker_outcome, since_ts, recheck_after_ts}`；coordinator 每 10min probe 写
`blocker_probe_result`；>7d 触发 ATLAS `blocked_too_long` (告警不解封)。

---

## §7 可观测性 (横切)

1. **per-account isolation** — 每账号独立 cooldown + scan reason；scan job 行带 `author_handle`
   + `tier` + `backend_id` + `reason`，账号间状态不共享 (O3 + N1 §4 风险 "不得跨 lease 共享 session state")。
2. **screenshot path** — 解析失败仅存 *路径* (post_record.screenshot_path)，落 Knowledge raw；
   图片二进制策略由 A4 OQ-07 决议 (路径 + DOM hash，不存 binary)。
3. **log redaction** — `SOLAR_HOTSPOT_X_API_TOKEN` 等 secret 不进 log / ledger / status payload；
   secret_scan 与 `forbid_optimistic_terms` 同级红线 (N3 §7.1 风险 #7)。

---

## §8 探索候选与 kill_criteria (Architecture Guard)

| 维度 | 候选 A (推荐) | 候选 B | kill_criteria |
|------|--------------|--------|--------------|
| dedup 位置 | extraction-time (写库前查 dedup_key) | ingest-time (inbox 临时表后台合并) | A: 跨进程 SQLite 锁 p99>200ms → 降 B；B: worker 滞后>5min → 升 A (留 A4/A2) |
| CLI 入口 | 扩展既有 `cmd_collect_social` | 新增 `cmd_collect_social_browser` | A: 与既有 `--source` 等参数命名冲突 → 降 B (留 A4) |
| operator_ready 探针 | lease 申请并立即释放 | Browser Agent registry 查询 | A: 产生真实 lease 占用记录开销 → 评估；B: 状态可能过时 (留 A4) |

> 排除项 C (新建独立 Playwright/Chrome 常驻 / 独立 Web 服务 / 新 ThunderOMLX 实例) 与 PRD
> 显式约束冲突，直接淘汰。

---

## §9 接口/数据 边界与旧系统兼容 (摘要，详见 A2/A3)

- **数据模型 DDL diff** (social_posts 新列 + social_post_dedup_keys 表) → A2 节点。
- **3-phase 迁移 + rollback env + 3 降级路径 + X API legacy 兼容** → A3 节点。
- **7 OQ 决议表** (OQ-01..07) → A4 节点。
- **traceability + S03 kickoff handoff** → A5 join 节点。

本 A1 只锁定控制平面 / 数据平面 / 7 接口 / 5 失败模式 / HardBlockerGuard；
下游 A2/A3/A4/A5 依赖本文件 `read_scope = A1-*.md`。

---

## §10 验收映射 (self-check)

| acceptance_id | 验收条目 | 本文件位置 |
|---------------|---------|-----------|
| A-A1-1 | 4-tier fallback locked + pick_backend(accounts, ctx)->(backend_id, reason) | §1.1 + §1.2 |
| A-A1-2 | RateLimiter 5 knobs 参数化 (cooldown/concurrency/jitter/backoff/freq) | §2 表 5 行 |
| A-A1-3 | 10 步数据平面 + model_call_ledger 3 写 | §3 + §3.1 |
| A-A1-4 | 7 接口签名 + acceptance | §4.1–§4.7 |
| A-A1-5 | 5 失败模式 + 观测钩子 | §5 表 5 行 |
| A-A1-6 | HardBlockerGuard sprint dispatch 检查 + raise BlockerNotResolved | §6.1 + §6.2 |

> 禁词自检 (父 task_graph evidence_policy.forbid_optimistic_terms 7 项)：本文件构造时
> 规避所有字面引用；以"锁定 / 参数化 / 覆盖 / 留 A4 决议"等等价语表达，不复制禁词字面值。
