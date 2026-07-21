# GitHub Hotspot Radar / Code Signal Plane

## 状态

Proposed

## 背景

Solar 当前已经有两条高度相近的 GitHub 任务线：

- `AI Influence GitHub Project Intelligence System Upgrade`
- `AI Influence GitHub Trend & Action Analyzer Ultimate`

两条线都在解决同一个核心问题：GitHub 模块不应停留在 Trending 榜单、repo 快照和 stars 增长，而应成为 AI Influence / Solar Research Radar 的代码信号层。

如果继续让这两条线并行演化，后果会是：

- 命名漂移：`project intelligence` / `trend analyzer` / `hotspot radar` 三套词并存
- 对象模型漂移：repo snapshot、evidence、scores、cards 多份 schema 分裂
- operator 漂移：重复 discovery / scoring / report 编译算子
- 输出漂移：daily/weekly report、repo cards、行动建议口径不一致

本 ADR 的目标是把 GitHub 模块正式收口为唯一主线：

```text
GitHub Hotspot Radar / Code Signal Plane
```

它在 Solar 三源共振体系中的职责是：

- `Paper Source` 回答研究界在想什么
- `Code Source` 回答开发者和开源社区在做什么
- `Influence Source` 回答社区和产业在聊什么

GitHub Hotspot Radar 是 `Code Source` 的主入口，负责把仓库活动、事件流、社区参与、release 节奏、依赖生态和跨源共振编译成：

- 社区介入建议
- AI Influence 选题
- Solar 集成机会
- 开源项目孵化 brief
- Deep Research seed

## 决策

### 1. 统一产品名和边界

GitHub 主线统一命名为：

```text
GitHub Hotspot Radar / Code Signal Plane
```

后续不再新增第三套同义 epic。现有两条线的定位调整为：

- `Project Intelligence System Upgrade`
  - 作为当前 runtime / schema / UI 演进主干
- `Trend & Action Analyzer Ultimate`
  - 作为 requirements / strategy 收口来源

统一后，所有新增设计、contract、operator、report、score、evidence 都以 `GitHub Hotspot Radar` 为唯一词汇表。

### 2. 统一产品定位

本模块不是：

- Trending 搬运
- stars 排行榜
- 新 repo 列表
- README 摘要器
- “这个项目很火”的无脑判断器

本模块必须回答四个问题：

1. 哪些开源项目正在起势？
2. 哪些技术方向正在形成社区势能？
3. 我们应该提前介入哪个社区、用什么方式介入？
4. 哪些热点方向可以反向驱动文章、实验、产品原型、开源项目？

### 3. 统一分层架构

采用 6 大执行层，而不是直接一次性做完全部 11 层：

```text
L0 Discovery
  -> L1 Snapshot + Canonicalization
  -> L2 Enrichment
  -> L3 Scoring
  -> L4 Insight Compiler
  -> L5 Resonance + Store
```

映射关系如下：

```text
完整愿景层:
  L0 Seed Discovery
  L1 Repo Snapshot
  L2 Canonicalization
  L3 Enrichment
  L4 Semantic Classification
  L5 Momentum Scoring
  L6 Community Graph
  L7 Direction Clustering
  L8 Opportunity Analysis
  L9 High Model Insight
  L10 Compiler
  L11 Store / Watch

首批实现层:
  Discovery
  Snapshot + Canonicalization
  Enrichment
  Scoring
  Insight Compiler
  Resonance + Store
```

首批不强求全量实现以下重层：

- 全量 GH Archive 历史大回放
- 全量 dependency graph 深度供应链建模
- 重图算法版 community graph
- 全自动 D0-D5 / S0-S5 生命周期分类闭环

### 4. 统一核心对象模型

以下对象模型成为 GitHub 线唯一事实源：

#### 4.1 RepoSnapshot

保存某一观察时刻的事实，不覆盖历史。

```json
{
  "snapshot_id": "gh_2026-05-27_daily_agent",
  "repo_key": "owner/repo",
  "observed_at": "2026-05-27T09:00:00-04:00",
  "source": "github_trending",
  "rank": 12,
  "stars": 1842,
  "forks": 155,
  "watchers": 28,
  "open_issues": 43,
  "pushed_at": "2026-05-27T04:21:00Z",
  "topics": ["ai-agent", "mcp", "workflow"],
  "language": "TypeScript"
}
```

#### 4.2 RepoCanonical

解决 rename、fork、mirror、template、demo 噪声。

```json
{
  "repo_key": "owner/repo",
  "github_node_id": "...",
  "owner": "owner",
  "name": "repo",
  "canonical_url": "...",
  "is_fork": false,
  "parent_repo": null,
  "is_archived": false,
  "is_template": false,
  "license": "MIT",
  "primary_language": "Python"
}
```

#### 4.3 RepoEnrichment

README、release、issues、PR、contributors 的结构化压缩层。

```json
{
  "repo_key": "owner/repo",
  "readme": {
    "summary": "...",
    "install_section_found": true,
    "quickstart_found": true,
    "api_docs_found": true
  },
  "activity": {
    "commits_7d": 32,
    "issues_opened_7d": 18,
    "prs_opened_7d": 12,
    "prs_merged_7d": 8,
    "release_count_30d": 3
  },
  "community": {
    "contributors_30d": 9,
    "new_contributors_30d": 4,
    "external_pr_ratio": 0.32,
    "maintainer_response_median_hours": 14
  }
}
```

#### 4.4 RepoSignal

多目标评分对象，不允许退化成单一 hot score。

```json
{
  "repo_key": "owner/repo",
  "signal_scores": {
    "github_hotspot": 0.82,
    "technical_substance": 0.74,
    "community_health": 0.69,
    "intervention_opportunity": 0.81,
    "open_project_opportunity": 0.73,
    "strategic_fit": 0.89,
    "noise_risk": 0.22
  },
  "signal_class": "serious_rising_project",
  "recommended_actions": [
    "try",
    "write_analysis",
    "build_integration",
    "deep_research_seed"
  ]
}
```

#### 4.5 GitHubEvidencePacket

高模型唯一合法输入，不允许直接吃 raw repo 列表。

```json
{
  "packet_type": "github_hotspot_packet",
  "packet_version": "v1",
  "repo": {},
  "ranking_signals": {},
  "activity_signals": {},
  "semantic_summary": {},
  "community_summary": {},
  "cross_source_refs": {},
  "local_scores": {},
  "questions_for_high_model": []
}
```

### 5. 统一评分体系

评分拆成 6 个目标，不用单一总分替代：

```text
1. GitHub Hotspot Score
2. Technical Substance Score
3. Community Health Score
4. Intervention Opportunity Score
5. Open Project Opportunity Score
6. Strategic Fit Score
```

关键原则：

- `velocity > absolute stars`
- `repo 热度 != 方向势能`
- `attention != substance`
- `社区可介入性` 必须单独建模
- `noise risk` 必须独立作为 gate

### 6. 统一产出资产

高模型和 deterministic compiler 最终至少产出以下资产：

- `GitHub Hotspot Card`
- `Direction Brief`
- `Community Intervention Plan`
- `Open-source Project Brief`
- `AI Influence Topic`
- `Deep Research Seed Pack`
- `Action Queue`

这些资产是 GitHub 模块向 Solar 其他系统输出的标准件，不再用 ad-hoc markdown 替代。

## MVP 算子切片

首批只强制打通 6 个 operator，其他都挂到下一阶段：

```text
1. GitHubCandidateDiscoveryOperator
2. RepoEnrichmentOperator
3. RepoSignalScoringOperator
4. GitHubEvidencePacketCompiler
5. GitHubHotspotInsightOperator
6. GitHubKnowledgeStoreOperator
```

### 1) GitHubCandidateDiscoveryOperator

职责：

- Trending snapshot
- GitHub Search discovery
- tracked repo watch list
- 外部 mention 抽取到 repo seed
- 基础 dedup

输入：

- topic filters
- tracked repo list
- discovery windows
- external mention packets

输出：

- candidate repo list
- raw discovery records
- repo seed provenance

### 2) RepoEnrichmentOperator

职责：

- repo metadata
- README 抓取与结构摘要
- releases / release assets
- issues / PR 摘要
- contributors 摘要
- contents light scan

输入：

- candidate repo list
- canonical repo identity

输出：

- `RepoSnapshot`
- `RepoCanonical`
- `RepoEnrichment`
- raw evidence atoms

### 3) RepoSignalScoringOperator

职责：

- hotspot / community / technical / intervention / open-project / strategic-fit / noise 评分
- short window spike 检测
- early-potential 检测
- hype / noise 判定

输入：

- snapshots
- enrichments
- external mentions

输出：

- `RepoSignal`
- repo class
- actionability flags

### 4) GitHubEvidencePacketCompiler

职责：

- 把 repo 相关的 raw facts 压缩成高模型可消费 packet
- 把 cross-source refs 结构化装进 packet
- 明确 questions-for-high-model

输出：

- `GitHubEvidencePacket`

### 5) GitHubHotspotInsightOperator

职责：

- 生成 repo card
- 生成 direction brief
- 生成 intervention plan
- 生成 open project brief
- 生成 deep research seed

说明：

- 高模型只看 packet
- 报告渲染尽量 deterministic
- 行动建议必须回指 grounding evidence

### 6) GitHubKnowledgeStoreOperator

职责：

- raw / extracted / qmd / graph 入库
- watchlist 状态维护
- 对三源共振层暴露标准查询面

## 三源共振接口合同

GitHub Hotspot Radar 作为 `Code Source`，向共振层输出：

```text
repo_signal
direction_cluster
community_intervention_plan
open_project_brief
deep_research_seed
cross_source_refs
```

与 `HF Paper Insight Flow` 的主要对齐字段：

```text
paper.method_tags        <-> repo.topic_tags
paper.project_page       <-> repo.linked_websites
paper.benchmark_keywords <-> repo.readme/release keywords
paper.org/author         <-> repo.owner/org
paper.asset refs         <-> repo / model / dataset / package refs
```

与 `Influence Source` 的主要对齐字段：

```text
repo mention urls
repo-linked GitHub URLs
maintainer / org mentions
topic keywords
direction cluster keywords
```

三源共振等级采用：

```text
G0 Code-only Spike
G1 Code + Community
G2 Code + Paper
G3 Code + Influence
G4 Paper + Code + Influence
G5 Sustained Resonance
```

## 噪声治理

必须保留独立 Noise Gate，不允许直接拿热点分覆盖噪声风险。

### fail 条件

- archived repo
- fork without independent momentum
- no code and not documentation project
- license missing for commercial relevance
- star spike without activity and without external validation

### downgrade 条件

- no release
- no tests
- no install instructions
- single maintainer no response

## 数据落盘结构

```text
raw/
  github_trending_snapshots/
  github_search_results/
  gharchive_events/
  repo_metadata/
  readme_raw/
  release_notes/
  issues_prs/

extracted/
  repo_cards/
  repo_signals/
  direction_clusters/
  intervention_plans/
  project_briefs/
  deep_research_seeds/

qmd/
  repo_index.qmd
  direction_index.qmd
  resonance_index.qmd

graph/
  repo_graph
  direction_graph
  resonance_graph
  action_graph
```

## 与现有线的合并策略

### 合并原则

```text
不要新建第三条 GitHub 主线
只允许把现有两条线收口到统一蓝图
```

### 映射关系

#### 现有线 A

`AI Influence GitHub Project Intelligence System Upgrade`

保留其已经完成和在推进的成果：

- discovery / snapshot / evidence / card / report 基础架构
- runtime / UI / report pipeline 的现有实现面

但今后其术语、contract、schema、输出口径，都要对齐本文 ADR。

#### 现有线 B

`AI Influence GitHub Trend & Action Analyzer Ultimate`

保留其 requirements / strategy 资产：

- action decision system
- intervention / open-source opportunity / resonance design

但其 requirements 产物应被视作：

```text
GitHub Hotspot Radar 统一主线的 strategy slice
```

而不是独立产品。

### 合并动作

1. GitHub 相关 PRD / contract / DAG 后续统一改用 `GitHub Hotspot Radar / Code Signal Plane`
2. 所有 schema 以 `RepoSnapshot / RepoCanonical / RepoEnrichment / RepoSignal / GitHubEvidencePacket` 为唯一真相
3. 所有输出以 `repo card / direction brief / intervention plan / open project brief / deep research seed` 为唯一资产面
4. 旧 `project intelligence` 与 `trend analyzer` 只作为历史切片，不再继续长出新名词

## 分阶段实施建议

### Phase 1: 统一真相层

- 收口命名
- 收口对象模型
- 收口评分字段
- 收口输出资产

### Phase 2: 打穿 6 个 MVP operator

- discovery
- enrichment
- scoring
- packet compiler
- insight
- store

### Phase 3: 接三源共振

- Paper Source 接口
- Influence Source 接口
- resonance matcher
- action queue compiler

### Phase 4: 重层能力

- deeper community graph
- direction clustering 强化
- GH Archive 历史趋势增强
- dependency graph / package ecosystem 深化

## 非目标

以下不是首批目标：

- 不把 GitHub 模块做成全功能 GitHub analytics 平台
- 不一开始就实现全量 GH Archive 长历史批分析
- 不先做超重 UI
- 不让高模型直接吞 raw repo 列表
- 不继续保留三套并行 GitHub 名词体系

## 后续执行建议

建议把现有 GitHub 主线后续工作全部压到下面 3 个 builder 入口：

```text
1. schema/runtime alignment
2. hotspot scoring + evidence packet compiler
3. insight compiler + resonance hooks
```

这样既不会推倒现有 `project intelligence` 进度，也能把你现在这版更强的 `Code Signal Plane` 设计变成唯一宪法。
