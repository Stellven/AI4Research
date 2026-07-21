# C1 — Dashboard Renderer Spec
# TH Social Browser Backend for X · S04 Orchestration-UI · X 大咖监控

epic_id: `epic-20260525-tech-hotspot-radar-social-browser-backend-for-x-大咖监控`
sprint_id: `sprint-20260525-tech-hotspot-radar-social-browser-backend-for-x-大咖监控-s04-orchestration-ui`
node: `C1`
role: planner
status: reviewing
generated_at: 2026-05-29
knowledge_context: solar-harness context inject used (QMD + Obsidian + Solar DB; mirage:timeout → fallback)
upstream: S02 A1 (StatusSurface interface, 7 indicators O8) + S03 C5 (status_surface.py + BackendSelector)
hard_blocker: `sprint-20260525-browser-agent-global-operator-cutover` — **mock-mode banner必须显示直到 blocker PASS**
package_boundary: `spec_only`

> **SPEC-ONLY CAVEAT**: 本文件是 Dashboard Renderer 渲染规约 (spec only)。  
> 不执行代码、不渲染真实 dashboard、不调 browser agent、不调 X API、不新起 ThunderOMLX。  
> 真渲染在 S05 V1 real e2e 中；mock-mode 下 banner 始终可见。

---

## §0 设计输入

| 输入 | 来源 | 用途 |
|------|------|------|
| O8 StatusSurface 7 indicators | S02 A1 §3 Interface-6 | §2 indicator card 定义 |
| S03 C5 status_surface.py | S03 core-runtime design §3 C5 | §5 data source binding |
| S03 C4 BackendSelector.pick() | S03 design §3 C4 + S02 A1 §1 | §5 last_run_status binding |
| hard_blocker guard | S02 A1 §3 Interface-7 + S03 design | §7 mock-mode banner |
| RateLimiter tier1/tier2 | S02 A1 §1 (per_account_cooldown + tier_freq) | §6 SLO row 扫描频率 |
| parse_fail threshold | O8 indicator + §6 SLO 规格 | §6 parse_fail rate ≥10% red |
| visual-template CSS vars | Tech Hotspot Radar overview template | §3 HTML template |
| Social Clusters section anchor | Tech Hotspot Radar overview layout | §3 嵌入位置 |

requirement_ids: `O8 (7 indicators), O1 (backend tier), O3 (rate), O9 (hard_blocker)`
acceptance_ids: `A-C1-1, A-C1-2, A-C1-3, A-C1-4, A-C1-5`

---

## §1 Dashboard 整体架构

### 1.1 渲染目标

X 大咖监控 dashboard 作为 **Tech Hotspot Radar overview** 页面中的一个独立区块嵌入，  
位于 Social Clusters section 之后（`<!-- @INSERT:social-browser-backend-x-dashboard -->`）。

该区块管理 **最多 200 个 X 账号**，展示三层信息：
1. **7 个指标卡 (indicator cards)** — 全局汇总状态，每次刷新轮询 status_surface.py
2. **TUI-style Rich 表格** — Top 10 活跃大咖 + per-backend 分布，可内嵌于 HTML
3. **SLO 行** — browser_ready 健康状态 + 扫描频率 + parse_fail 告警

顶部始终检测 `HardBlockerGuard.check_blocker()` 结果；若未 PASS 则显示全宽 banner。

### 1.2 渲染入口 (spec 层接口)

```python
# 调用方式 (S05 真渲染时实现)
from lib.social_browser_backend_x.status_surface import StatusSurface
from lib.social_browser_backend_x.backend_selector import BackendSelector

surface = StatusSurface()
indicators = surface.get_indicators()    # → dict[str, Any]  (7 keys per O8)
last_run   = BackendSelector.last_run_status()  # → LastRunStatus dataclass

# 渲染器消费上面两个对象，输出:
# (a) HTML fragment (嵌入 overview)
# (b) Rich console 表格 (TUI)
```

### 1.3 数据刷新策略

| 场景 | 刷新方式 | 频率 |
|------|----------|------|
| HTML overview (浏览器) | JS `fetch('/api/social-status')` 轮询 | 60s |
| TUI 终端 | `rich.live.Live` + `StatusSurface.get_indicators()` 轮询 | 30s |
| CI / report snapshot | 单次调用，无轮询 | on-demand |

---

## §2 7 个指标卡 (Indicator Cards) 详细规格

每张卡的数据全部来自 `StatusSurface.get_indicators()` 返回值，键名对应 O8 定义。

### §2.1 卡片一览表

| # | 卡名 (display) | 数据键 | 类型 | 格式 | 健康阈值 |
|---|---------------|--------|------|------|----------|
| 1 | Total Accounts | `total` | int | `N` (裸数字) | 无 (info 卡) |
| 2 | Enabled | `enabled` | int | `N` | `> 0` 才有意义 |
| 3 | Scanned Today | `scanned_today` | int | `N / enabled` | 无 |
| 4 | Browser Ready | `browser_ready` | bool / str | ✅ / ⚠️ / ❌ | 见 §6 SLO |
| 5 | Scan State | `scan_state` | enum | idle / running / backoff | 无 (状态卡) |
| 6 | Parse Fail | `parse_fail` | float | `X.X%` | ≥10% → red |
| 7 | Fallback Count + By Backend | `fallback_count` + `by_backend_count` | int + dict | `N (tier B / tier R / tier M)` | 见 §2.8 |

> `by_backend_count` 在 O8 定义中是单独 indicator，本卡合并展示以节省宽度。
> HTML 版本分两行展示；TUI 版本在 Rich table per-backend share 列中展示（§4）。

### §2.2 Card-1: Total Accounts

```
标签:  Total Accounts
值:    indicators['total']            # int, 期望值 ≤ 200
颜色:  white (neutral)
备注:  包含所有账号，不论 enabled 状态
```

### §2.3 Card-2: Enabled

```
标签:  Enabled
值:    indicators['enabled']          # int
颜色:  green  (> 0)
       yellow (== 0, 警告: 没有启用账号)
备注:  仅 enabled=True 的账号参与调度
```

### §2.4 Card-3: Scanned Today

```
标签:  Scanned Today
值:    "{indicators['scanned_today']} / {indicators['enabled']}"
颜色:  green  (scanned_today / enabled ≥ 0.8)
       yellow (0.4 ≤ rate < 0.8)
       red    (rate < 0.4, 超过 60% 账号今天未扫描)
备注:  每日 UTC 00:00 重置计数器
```

### §2.5 Card-4: Browser Ready

```
标签:  Browser Ready
值:    ✅ / ⚠️ / ❌  (见 §6 SLO 定义)
颜色:  green / yellow / red
备注:  直接映射 indicators['browser_ready'] 到 SLO 三态
       若 HardBlockerGuard.check_blocker() == False → 强制显示 ❌ + "(mock)"
```

### §2.6 Card-5: Scan State

```
标签:  Scan State
值:    indicators['scan_state']       # enum: idle | running | backoff | error
颜色:  blue   (running)
       white  (idle)
       yellow (backoff)
       red    (error)
备注:  backoff 时附加 last_run.backoff_until 时间戳
```

### §2.7 Card-6: Parse Fail

```
标签:  Parse Fail
值:    "{indicators['parse_fail'] * 100:.1f}%"
颜色:  green  (rate < 0.05)
       yellow (0.05 ≤ rate < 0.10)
       red    (rate ≥ 0.10)   ← §6 SLO 硬线
备注:  parse_fail = parsed_fail_count / total_attempted (24h 滑动窗口)
       ≥10% 时 SLO 行同步标红（§6）
```

### §2.8 Card-7: Fallback + By Backend

```
标签:  Fallbacks  /  By Backend
行1:   "Fallbacks: {indicators['fallback_count']}"
       fallback_count = 本日 browser_agent→rss/manual 切换次数

行2:   "browser: N  |  rss: N  |  manual: N  |  x_api: N"
       值来自 indicators['by_backend_count'] dict:
         {
           "browser_agent":  int,
           "rss_public":     int,
           "manual_curated": int,
           "x_api_optional": int
         }
颜色:  neutral (info 卡)；若 browser_agent == 0 且 HardBlockerGuard 未 PASS → yellow
```

---

## §3 HTML Template 规格

### §3.1 嵌入位置

Tech Hotspot Radar overview HTML 文件在 Social Clusters section 结束后插入占位符：

```html
<!-- @INSERT:social-clusters-end -->
<!-- @INSERT:social-browser-backend-x-dashboard -->
```

Dashboard fragment 替换第二个占位符整块内容。

### §3.2 CSS 变量绑定 (visual-template)

以下 CSS 变量由 visual-template 主题文件统一定义；dashboard fragment **不得硬编码颜色值**，  
必须通过这些变量引用：

| CSS 变量 | 用途 | 期望值 (dark theme 参考) |
|----------|------|--------------------------|
| `--vt-bg-card` | 卡片背景 | `#1a1a2e` |
| `--vt-bg-section` | section 背景 | `#16213e` |
| `--vt-border` | 卡片边框 | `#0f3460` |
| `--vt-text-primary` | 主文字 | `#e0e0e0` |
| `--vt-text-secondary` | 次要文字 / 标签 | `#888` |
| `--vt-accent-green` | 健康 / OK | `#00d084` |
| `--vt-accent-yellow` | 警告 | `#f4d03f` |
| `--vt-accent-red` | 告警 / 错误 | `#e74c3c` |
| `--vt-accent-blue` | 活跃 / 运行中 | `#3498db` |
| `--vt-accent-white` | 中性 / idle | `#ecf0f1` |
| `--vt-banner-bg` | mock-mode banner 背景 | `#2c3e50` |
| `--vt-banner-border` | mock-mode banner 边框 | `#f4d03f` |

### §3.3 HTML Fragment 结构

```html
<!-- S: social-browser-backend-x-dashboard -->
<section
  id="social-browser-backend-x-dashboard"
  class="vt-section social-backend-dashboard"
  data-refresh-url="/api/social-status"
  data-refresh-interval="60">

  <!-- §7 Hard Blocker Banner (conditional) -->
  <div id="social-blocker-banner"
       class="vt-banner-warn"
       data-show-when="hard_blocker_active"
       style="display:none">
    ⚠️ <strong>Browser Agent upstream not ready, running in mock-mode</strong>
    &nbsp;—&nbsp;实时数据不可用；以下数据来自 fixture/mock 返回值。
    <span class="vt-banner-meta">
      Blocker: sprint-20260525-browser-agent-global-operator-cutover
    </span>
  </div>

  <!-- Section Header -->
  <h3 class="vt-section-title">
    𝕏 大咖监控
    <span class="vt-badge" id="social-account-count">— / 200</span>
  </h3>

  <!-- §2 Indicator Cards Grid (7 cards) -->
  <div class="vt-cards-grid social-indicator-cards" role="list">

    <div class="vt-card" id="card-total" role="listitem">
      <span class="vt-card-label">Total Accounts</span>
      <span class="vt-card-value" data-bind="indicators.total">—</span>
    </div>

    <div class="vt-card" id="card-enabled" role="listitem">
      <span class="vt-card-label">Enabled</span>
      <span class="vt-card-value" data-bind="indicators.enabled"
            data-color-rule="enabled_color">—</span>
    </div>

    <div class="vt-card" id="card-scanned-today" role="listitem">
      <span class="vt-card-label">Scanned Today</span>
      <span class="vt-card-value" data-bind="indicators.scanned_today_ratio"
            data-color-rule="scanned_ratio_color">— / —</span>
    </div>

    <div class="vt-card" id="card-browser-ready" role="listitem">
      <span class="vt-card-label">Browser Ready</span>
      <span class="vt-card-value vt-slo-indicator"
            data-bind="indicators.browser_ready_slo">—</span>
    </div>

    <div class="vt-card" id="card-scan-state" role="listitem">
      <span class="vt-card-label">Scan State</span>
      <span class="vt-card-value" data-bind="indicators.scan_state"
            data-color-rule="scan_state_color">—</span>
      <span class="vt-card-sub" data-bind="indicators.backoff_until"
            data-show-when="scan_state==backoff"></span>
    </div>

    <div class="vt-card" id="card-parse-fail" role="listitem">
      <span class="vt-card-label">Parse Fail</span>
      <span class="vt-card-value" data-bind="indicators.parse_fail_pct"
            data-color-rule="parse_fail_color">—</span>
    </div>

    <div class="vt-card vt-card-wide" id="card-fallback" role="listitem">
      <span class="vt-card-label">Fallbacks / By Backend</span>
      <span class="vt-card-value" data-bind="indicators.fallback_count">—</span>
      <div class="vt-backend-share" data-bind="indicators.by_backend_count">
        <span class="vt-be-browser">browser: —</span>
        <span class="vt-be-rss">rss: —</span>
        <span class="vt-be-manual">manual: —</span>
        <span class="vt-be-xapi">x_api: —</span>
      </div>
    </div>

  </div><!-- /vt-cards-grid -->

  <!-- §4 Top-10 TUI Rich Table (embedded as styled table) -->
  <div class="vt-subsection" id="social-top10-table">
    <h4 class="vt-subsection-title">Top 10 活跃大咖</h4>
    <table class="vt-rich-table social-top10"
           aria-label="Top 10 活跃大咖 按 per-backend 分布">
      <thead>
        <tr>
          <th>#</th>
          <th>Handle</th>
          <th>Tier</th>
          <th>Last Scan</th>
          <th>Posts Today</th>
          <th>Backend</th>
          <th>Parse Fail</th>
          <th>State</th>
        </tr>
      </thead>
      <tbody id="social-top10-body" data-bind="top10_accounts">
        <!-- rows injected by JS or server-side render -->
      </tbody>
    </table>
  </div>

  <!-- §6 SLO Row -->
  <div class="vt-slo-row" id="social-slo-row" role="status" aria-live="polite">
    <span class="vt-slo-item" id="slo-browser-ready">
      Browser Ready: <span data-bind="slo.browser_ready_icon">—</span>
    </span>
    <span class="vt-slo-separator">|</span>
    <span class="vt-slo-item">
      Tier1 (P0): <span data-bind="slo.tier1_freq">6h</span>
    </span>
    <span class="vt-slo-separator">|</span>
    <span class="vt-slo-item">
      Tier2: <span data-bind="slo.tier2_freq">24h</span>
    </span>
    <span class="vt-slo-separator">|</span>
    <span class="vt-slo-item" id="slo-parse-fail"
          data-color-rule="parse_fail_color">
      Parse Fail: <span data-bind="slo.parse_fail_display">—</span>
    </span>
  </div>

</section>
<!-- E: social-browser-backend-x-dashboard -->
```

### §3.4 CSS 样式规则 (fragment-level, variables-only)

```css
/* social-browser-backend-x-dashboard.css — 仅限 CSS 变量引用 */

.social-backend-dashboard {
  background: var(--vt-bg-section);
  border: 1px solid var(--vt-border);
  border-radius: 8px;
  padding: 16px;
  margin-top: 24px;
}

.social-indicator-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.vt-card-wide {
  grid-column: span 2;
}

/* Color rules applied via JS data-color-rule bindings */
[data-color-rule="parse_fail_color"][data-value-level="ok"]   { color: var(--vt-accent-green); }
[data-color-rule="parse_fail_color"][data-value-level="warn"] { color: var(--vt-accent-yellow); }
[data-color-rule="parse_fail_color"][data-value-level="red"]  { color: var(--vt-accent-red); }

[data-color-rule="scan_state_color"][data-value="running"]    { color: var(--vt-accent-blue); }
[data-color-rule="scan_state_color"][data-value="idle"]       { color: var(--vt-accent-white); }
[data-color-rule="scan_state_color"][data-value="backoff"]    { color: var(--vt-accent-yellow); }
[data-color-rule="scan_state_color"][data-value="error"]      { color: var(--vt-accent-red); }

/* Mock-mode banner */
.vt-banner-warn {
  background: var(--vt-banner-bg);
  border: 1px solid var(--vt-banner-border);
  border-radius: 4px;
  color: var(--vt-accent-yellow);
  padding: 8px 12px;
  margin-bottom: 12px;
  font-size: 0.9rem;
}

/* SLO row */
.vt-slo-row {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 0.85rem;
  color: var(--vt-text-secondary);
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--vt-border);
}
```

### §3.5 JS 数据绑定协议 (Data Bind Contract)

JavaScript 渲染器轮询 `/api/social-status` 并将 JSON 映射到 `data-bind` 属性：

```typescript
// API 响应结构 (S05 真渲染实现)
interface SocialStatusResponse {
  indicators: {
    total:            number;
    enabled:          number;
    scanned_today:    number;
    browser_ready:    boolean | "mock";
    scan_state:       "idle" | "running" | "backoff" | "error";
    parse_fail:       number;          // [0.0, 1.0]
    fallback_count:   number;
    by_backend_count: {
      browser_agent:  number;
      rss_public:     number;
      manual_curated: number;
      x_api_optional: number;
    };
  };
  slo: {
    browser_ready_icon:  "✅" | "⚠️" | "❌";
    tier1_freq:          "6h";
    tier2_freq:          "24h";
    parse_fail_display:  string;       // e.g. "3.2%" or "12.5% ⚠"
  };
  top10_accounts: Top10Row[];
  hard_blocker_active: boolean;
  generated_at: string;               // ISO 8601
}
```

---

## §4 TUI Rich Table 规格

### §4.1 Rich console 表格 (TUI 渲染)

当 `render_mode=tui` 时，使用 Python `rich` 库渲染到终端：

```
┌─────────────────────────────────── 𝕏 大咖监控 (200 accounts) ───────────────────────────────────┐
│ ⚠️  Browser Agent upstream not ready, running in mock-mode                                        │  ← mock-mode 时显示
└────────────────────────────────────────────────────────────────────────────────────────────────────┘

  Total: 200  │  Enabled: 185  │  Scanned Today: 142/185  │  Browser Ready: ❌ (mock)
  Scan State: idle  │  Parse Fail: 2.3%  │  Fallbacks: 0  │  By Backend: browser:0  rss:142  manual:0  x_api:0

 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ Top 10 活跃大咖 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 #  │ Handle           │ Tier  │ Last Scan    │ Posts Today │ Backend   │ Parse Fail │ State
────┼──────────────────┼───────┼──────────────┼─────────────┼───────────┼────────────┼──────────
 1  │ @handle_a        │  P0   │ 2h 15m ago   │      8      │ rss       │  0.0%      │ idle
 2  │ @handle_b        │  P0   │ 3h 02m ago   │      6      │ rss       │  0.0%      │ idle
 3  │ @handle_c        │  P0   │ 5h 48m ago   │      5      │ rss       │  1.2%      │ backoff
 4  │ @handle_d        │  T2   │ 10h 30m ago  │      4      │ manual    │  0.0%      │ idle
 5  │ @handle_e        │  P0   │ 6h 00m ago   │      3      │ rss       │  0.0%      │ idle
 6  │ @handle_f        │  T2   │ 12h 00m ago  │      3      │ rss       │  5.1%      │ idle
 7  │ @handle_g        │  P0   │ 5h 59m ago   │      3      │ rss       │  0.0%      │ idle
 8  │ @handle_h        │  T2   │ 14h 22m ago  │      2      │ manual    │  0.0%      │ idle
 9  │ @handle_i        │  T2   │ 19h 01m ago  │      2      │ rss       │  2.3%      │ idle
10  │ @handle_j        │  P0   │ 5h 55m ago   │      1      │ rss       │  0.0%      │ idle

 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 SLO  │ Browser: ❌ (mock)  │  Tier1 freq: 6h  │  Tier2 freq: 24h  │  Parse Fail: 2.3% ✅
```

### §4.2 Rich 列定义

| 列名 | 数据来源 | 宽度 | 对齐 | 颜色规则 |
|------|----------|------|------|----------|
| `#` | rank (1-10) | 3 | right | neutral |
| `Handle` | account.handle | 18 | left | neutral |
| `Tier` | account.tier → "P0" / "T2" | 5 | center | P0=yellow, T2=white |
| `Last Scan` | account.last_scanned_at → relative | 14 | right | >6h(P0)/24h(T2)=yellow |
| `Posts Today` | account.posts_today | 12 | center | >0=green, 0=white |
| `Backend` | account.last_backend | 10 | left | browser=green(mock时=dim), rss=blue, manual=white, x_api=dim |
| `Parse Fail` | account.parse_fail_rate | 10 | right | <5%=green, 5-10%=yellow, ≥10%=red |
| `State` | account.scan_state | 8 | left | idle=white, running=blue, backoff=yellow, error=red |

### §4.3 Per-Backend Share (底部汇总行)

TUI 表格下方额外输出一行 per-backend 占比：

```
 Per-backend share (scanned_today=142):
   browser_agent:  0   (0.0%)   [mock-mode: 不可用]
   rss_public:    130  (91.5%)
   manual_curated: 12  (8.5%)
   x_api_optional:  0  (0.0%)
```

颜色：dominant backend (占比 ≥50%) 用 `--vt-accent-blue`；mock-mode 时 browser_agent 用 dim red。

### §4.4 Top 10 排序规则

```
优先级 (降序):
  1. posts_today desc            (今日发帖最多的账号优先)
  2. tier asc (P0 before T2)    (同 posts_today 时 P0 账号优先)
  3. last_scanned_at desc        (最近扫描的优先)
  4. handle asc                  (tie-break)
```

---

## §5 数据源绑定

### §5.1 StatusSurface 绑定

S03 C5 产出的 `lib/social_browser_backend_x/status_surface.py`：

```python
# 接口规约 (S03 C5 产出, S04 C1 消费)
class StatusSurface:
    def get_indicators(self) -> dict:
        """
        Returns dict with exactly 7 top-level keys (per O8):
          total:            int     # all accounts in config
          enabled:          int     # enabled=True accounts
          scanned_today:    int     # successfully scanned in last 24h UTC
          browser_ready:    bool    # HardBlockerGuard.check_blocker() == True
                                    # AND BrowserLeaseClient last ping OK
          scan_state:       str     # "idle" | "running" | "backoff" | "error"
          parse_fail:       float   # [0.0, 1.0] 24h rolling window
          fallback_count:   int     # fallback events today
          by_backend_count: dict    # {backend_id: int} for all 4 tiers
        """

    def get_top10(self) -> list[dict]:
        """
        Returns list of up to 10 dicts, each with keys:
          handle, tier, last_scanned_at, posts_today,
          last_backend, parse_fail_rate, scan_state
        Sorted per §4.4 ordering rules.
        """
```

### §5.2 BackendSelector.last_run_status() 绑定

S03 C4 BackendSelector 扩展方法，由 S04 C1 spec 规约：

```python
# S03 C4 产出 / S04 C1 消费
@classmethod
def last_run_status(cls) -> "LastRunStatus":
    """
    Returns LastRunStatus dataclass:
      selected_backend: str          # 上次实际选用的 backend id
      reason:           str          # selector 决策原因
      timestamp:        datetime
      backoff_until:    datetime | None   # 若 scan_state==backoff
      hard_blocker_active: bool      # True = HardBlockerGuard 检测到 blocker 未 PASS
    """
```

### §5.3 绑定映射表

| dashboard 元素 | 数据键路径 | 来源方法 |
|----------------|-----------|----------|
| Card-1 Total | `indicators['total']` | StatusSurface.get_indicators() |
| Card-2 Enabled | `indicators['enabled']` | StatusSurface.get_indicators() |
| Card-3 Scanned Today | `indicators['scanned_today']` | StatusSurface.get_indicators() |
| Card-4 Browser Ready | `indicators['browser_ready']` | StatusSurface.get_indicators() |
| Card-5 Scan State | `indicators['scan_state']` | StatusSurface.get_indicators() |
| Card-6 Parse Fail | `indicators['parse_fail']` | StatusSurface.get_indicators() |
| Card-7 Fallback+ByBackend | `indicators['fallback_count']` + `indicators['by_backend_count']` | StatusSurface.get_indicators() |
| Top 10 rows | `top10` | StatusSurface.get_top10() |
| SLO browser_ready | `last_run.hard_blocker_active` | BackendSelector.last_run_status() |
| SLO backoff_until | `last_run.backoff_until` | BackendSelector.last_run_status() |
| Banner 显示条件 | `last_run.hard_blocker_active == True` | BackendSelector.last_run_status() |

---

## §6 SLO 行定义

### §6.1 browser_ready 三态

| 图标 | 条件 | 说明 |
|------|------|------|
| ✅ | `indicators['browser_ready'] == True` AND `HardBlockerGuard.check_blocker() == True` | Browser Agent 可用，无 mock |
| ⚠️ | `indicators['browser_ready'] == True` BUT 最近 1h 内有 OperatorNotReady 事件 | 可用但不稳定 |
| ❌ | `HardBlockerGuard.check_blocker() == False` OR `indicators['browser_ready'] == False` | 不可用；mock-mode 生效时必然是 ❌ |

### §6.2 扫描频率 SLO 行

```
SLO 行固定显示内容 (不随数据变化，仅 browser_ready 图标动态):
  Browser Ready: {icon}  |  Tier1 (P0): 6h  |  Tier2: 24h  |  Parse Fail: {value}
```

`Tier1 freq = 6h` 和 `Tier2 freq = 24h` 来自 S02 A1 §1 RateLimiter 固定参数；  
不从运行时读取（避免误改 SLO 标准）。

### §6.3 parse_fail rate SLO 颜色

```
parse_fail <  5%  →  green  "X.X% ✅"
parse_fail 5-10%  →  yellow "X.X% ⚠"
parse_fail ≥ 10%  →  red    "X.X% ❌"   ← SLO 违反线
```

parse_fail ≥10% 时：
- SLO 行 parse_fail 值标红
- Card-6 标红
- Top 10 表中该账号的 Parse Fail 列标红

---

## §7 Hard Blocker Banner

### §7.1 触发条件

```python
# 检测方式 (渲染器调用)
from lib.social_browser_backend_x.hard_blocker_guard import HardBlockerGuard
hard_blocker_active = not HardBlockerGuard.check_blocker(
    sprint_id="sprint-20260525-browser-agent-global-operator-cutover"
)
```

`hard_blocker_active == True` → banner 显示；`False` → banner 隐藏。

### §7.2 Banner 内容规格

**全宽黄色警告条**，固定文案（不得修改）：

```
⚠️  Browser Agent upstream not ready, running in mock-mode
    Blocker: sprint-20260525-browser-agent-global-operator-cutover
    [data shown below is from mock fixtures, not real X accounts]
```

### §7.3 显示规则

| 位置 | 规则 |
|------|------|
| HTML dashboard | `id="social-blocker-banner"` 在 section header 上方；`display:none` 切换为 `display:block` |
| TUI 表格 | 第二行（在标题行后）；用 `rich.panel.Panel` yellow border |
| Report snapshot | 在 markdown 输出的第一行加 `> ⚠️ mock-mode` blockquote |

### §7.4 mock-mode 对 card 值的影响

| 指标 | mock-mode 时的显示 |
|------|--------------------|
| `browser_ready` | `❌ (mock)` |
| `by_backend_count.browser_agent` | 0 + dim red |
| `scan_state` | 来自 fixture，不反映真实状态 |
| Top 10 Backend 列 | 所有 `browser_agent` 显示为 `rss (mock fallback)` |

---

## §8 验收标准

| ID | 验收条件 |
|----|---------|
| A-C1-1 | 200 account dashboard 所有 7 indicator cards 完整定义（数据键、格式、颜色规则、阈值） |
| A-C1-2 | HTML template 使用 visual-template CSS 变量，嵌入位置在 Social Clusters section 之后，无硬编码颜色值 |
| A-C1-3 | TUI Rich table 定义 Top 10 活跃大咖，含 8 列、per-backend share 汇总行、排序规则 |
| A-C1-4 | 数据源绑定文档：status_surface.py 接口签名 (7 keys) + BackendSelector.last_run_status() 签名，映射表完整 |
| A-C1-5 | hard_blocker banner 显示条件、固定文案、三渲染模式规则均已明确；mock-mode 对各 card 的影响列表完整 |

---

## §9 非目标

- 不实施渲染代码（spec_only）
- 不真调 X API 或 browser agent
- 不新起 ThunderOMLX 实例
- 不修改 `lib/social_browser_backend_x/` (read-only in S04)
- 不绕过 HardBlockerGuard
- 不硬编码账号列表、handle、测试数据
- 不实现 `/api/social-status` 真实端点（S05 scope）

---

## §10 下游依赖

| 下游节点 | 消费内容 |
|---------|---------|
| S04 C2 CLI cmd tree | CLI `solar-harness wiki tech-hotspot-radar collect-social --status` 输出格式参考 §4 TUI |
| S04 C5 traceability | A-C1-1 ～ A-C1-5 验收项映射到 traceability.json |
| S05 V1 real e2e | §3 HTML template + §5 data binding 实现为真实渲染代码 |
| S05 V2 SLO 验证 | §6 parse_fail ≥10% red 阈值 + §6.2 scan freq 固定值为 SLO 基准 |
