# AI Influence Insight / Social Signal Plane

## 状态

Proposed

## 背景

Solar Research Radar 需要三源共振：

- `Paper Source`：研究界在发明什么
- `Code Source`：开发者和开源社区在实现什么
- `Influence Source`：大咖、机构、会议、公司和资本市场在押注什么

当前 Solar 本地已经有若干社交相关切片：

- `Tech Hotspot Radar: Social Browser Backend for X 大咖监控`
- YouTube transcript / caption / ASR 分层重构
- AI Influence 社交趋势报告与 knowledge raw 入库链

这些切片解决的是采集、caption、fallback、证据质量等局部能力，但还没有形成统一的 `Influence Source` 主线宪法。

如果继续把社交模块理解为：

- X timeline 抓取
- 大咖帖子汇总
- 热门 tweet 摘要
- 观点搬运

那么最终得到的只会是低价值舆情流水账，而不是可驱动研究、文章、Deep Research 和开源项目的信号系统。

本 ADR 的目标是正式把社交大咖模块收口为：

```text
AI Influence Insight / Social Signal Plane
```

一句话定义：

```text
把“大咖观点”编译成“技术命题、证据映射、路线冲突、趋势共振和可执行机会”。
```

## 决策

### 1. 统一产品定位

本模块不是：

- 社交搬运
- 粉丝榜
- 转赞评榜
- 热门 tweet 摘要
- “谁说了什么”的流水账

本模块必须做的是：

1. 识别大咖观点背后的技术命题
2. 判断该观点是否代表产业风向或路线押注
3. 反向搜索论文、代码、会议、产品、财经和重大事件证据
4. 识别观点之间的一致、冲突、反转和路线竞争
5. 输出 AI Influence 选题、Deep Research seed、开源项目 brief、行动队列

### 2. 与现有本地线的层级关系

必须明确：

```text
X / Browser / Timeline 采集
  只是 Social Signal Plane 的 L1 收集层

YouTube transcript / caption / ASR
  只是 Social Signal Plane 的长内容证据层

AI Influence Insight / Social Signal Plane
  才是整个 Influence Source 的主线系统
```

因此现有 `social-browser-backend-for-x-大咖监控` 不应再被当成完整社交洞察产品，而应降级为：

```text
Social Signal Plane 的 source collection slice
```

### 3. 统一分层架构

采用 6 大执行层收口首批实现：

```text
L0 Seed Registry
  -> L1 Statement Collection + Normalization
  -> L2 Thesis Extraction + Viewpoint Graph
  -> L3 Evidence Mapping
  -> L4 Insight Compiler
  -> L5 Resonance + Store
```

映射回完整愿景层如下：

```text
完整愿景层:
  L0 Account / Source Seed
  L1 Statement Collection
  L2 Identity Resolution
  L3 Statement Normalization
  L4 Thesis Extraction
  L5 Viewpoint Graph
  L6 Search Planner
  L7 Evidence Retrieval
  L8 Resonance Analysis
  L9 High Model Insight
  L10 Compiler
  L11 Knowledge Store

首批实现层:
  Seed Registry
  Statement Collection + Normalization
  Thesis Extraction + Viewpoint Graph
  Evidence Mapping
  Insight Compiler
  Resonance + Store
```

首批不强求全量实现：

- 所有社交平台同时接入
- 全量 conference / finance / policy connector 深度打通
- 超重的长期准确率回溯系统
- 全自动 stance reversal 全时序追踪

### 4. 统一核心对象模型

#### 4.1 InfluencerProfile

人物、机构、平台账号与角色上下文的唯一真相对象。

```json
{
  "influencer_id": "person:sam_altman",
  "display_name": "...",
  "current_role": "...",
  "organization": "...",
  "tier": "T0",
  "categories": ["core_leader", "ai_lab"],
  "platform_accounts": {
    "x": "...",
    "bluesky": "...",
    "youtube": "...",
    "blog": "...",
    "github": "..."
  },
  "expertise_tags": ["foundation_models", "agent", "ai_infra"],
  "bias_profile": {
    "vendor_affiliated": true,
    "investor": false,
    "open_source_advocate": false
  },
  "historical_accuracy_score": 0.72,
  "influence_weight": 0.86
}
```

关键要求：

- 必须支持 `role_at_time`
- 观点权重必须和说话时角色绑定

#### 4.2 Statement

原始观点容器，不允许直接跳过 Statement 去做高模型总结。

```json
{
  "statement_id": "stmt_20260527_0001",
  "influencer_id": "person:...",
  "source_type": "x_post",
  "source_url": "...",
  "published_at": "2026-05-27T09:00:00Z",
  "collected_at": "2026-05-27T10:00:00Z",
  "raw_text": "...",
  "normalized_text": "...",
  "language": "en",
  "entities": ["OpenAI", "agent", "MCP"],
  "engagement": {
    "likes": 0,
    "reposts": 0,
    "comments": 0,
    "views": 0
  },
  "quality_flags": {
    "is_quote": false,
    "is_reply": false,
    "is_joke_or_meme": false,
    "is_marketing": false,
    "transcript_quality": "manual"
  }
}
```

#### 4.3 Thesis

社交模块的真正分析对象。Statement 只是来源，Thesis 才是研究对象。

```json
{
  "thesis_id": "thesis_agent_memory_infra_20260527",
  "statement_ids": ["stmt_001", "stmt_032"],
  "thesis_type": "technical_judgment",
  "topic": "agent memory infrastructure",
  "claim": "Agent memory is becoming a core infrastructure layer rather than an application feature.",
  "modality": "asserted",
  "time_horizon": "6-18m",
  "confidence": 0.74,
  "stance": "support",
  "entities": ["agent", "memory", "RAG", "state management"],
  "source_influencers": ["person:...", "person:..."],
  "viewpoint_cluster": "agent_infra"
}
```

#### 4.4 InfluenceEvidencePacket

高模型唯一允许消费的结构化输入包。

```json
{
  "packet_type": "influence_evidence_packet",
  "packet_version": "v1",
  "time_window": {
    "start": "2025-11-27",
    "end": "2026-05-27"
  },
  "thesis": {},
  "speaker_signals": [],
  "mapped_evidence": {
    "papers": [],
    "github_repos": [],
    "hf_assets": [],
    "conference_events": [],
    "company_releases": [],
    "financial_events": [],
    "major_news": []
  },
  "local_scores": {
    "influence_momentum": 0.81,
    "cross_source_resonance": 0.74,
    "technical_substance": 0.69,
    "market_relevance": 0.78,
    "controversy": 0.42,
    "actionability": 0.83,
    "noise_risk": 0.21
  },
  "questions_for_high_model": []
}
```

### 5. 统一观点映射逻辑

Social Signal Plane 的核心不是采集，而是：

```text
Statement
  -> Thesis
  -> Query Plan
  -> Evidence Mapping
  -> Resonance / Contradiction / Actionability
```

例如：

```text
大咖说：
  Agent memory is going to be the real bottleneck.

系统抽成 thesis：
  agent memory 正在从应用功能变成基础设施瓶颈

自动映射搜索：
  - paper
  - GitHub
  - HF assets
  - conferences
  - product releases
  - finance / SEC / earnings
  - major news / GDELT
```

### 6. 统一评分体系

社交层必须至少有 7 个分，不允许只看 engagement。

```text
1. Influence Momentum Score
2. Thesis Materiality Score
3. Cross-source Resonance Score
4. Controversy / Contradiction Score
5. Actionability Score
6. Noise Risk Score
7. Strategic Fit Score
```

关键原则：

- `speaker tier != truth`
- `engagement != materiality`
- `social-only` 不能直接进高结论
- `观点冲突` 本身是高价值信号，不是噪声

### 7. 信号分层

Influence 信号统一分层为：

```text
I0 Raw Mention
I1 Notable Statement
I2 Repeated Viewpoint
I3 Mapped Thesis
I4 Cross-source Resonance
I5 Strategic Insight
I6 Action Trigger
I7 Route Shift
```

这层分级直接服务 AI Influence、Deep Research 和开源项目动作，而不是热度榜展示。

## MVP 算子切片

首批只强制打通 7 个 operator：

```text
1. InfluencerSeedRegistry
2. StatementCollector
3. StatementNormalizer
4. ThesisExtractionOperator
5. ThesisMappingOperator
6. InfluenceEvidencePacketCompiler
7. InfluenceInsightCompiler
```

### 1) InfluencerSeedRegistry

职责：

- 管理 influencer / org / source seed
- tier / category / topic tags
- role_at_time 基础元数据

输入：

- curated account lists
- org / company / conference source lists

输出：

- `InfluencerProfile`
- source registry

### 2) StatementCollector

职责：

- 首批接入 X / Bluesky / YouTube / Blog / HN 中最稳的几个
- 采集 raw post / thread / transcript / blog / discussion

输出：

- raw statements
- source metadata
- collection provenance

### 3) StatementNormalizer

职责：

- 时间、语言、实体、来源统一化
- quote / reply / meme / marketing / transcript quality 标记

输出：

- normalized `Statement`

### 4) ThesisExtractionOperator

职责：

- 从 statement 抽 `claim / topic / stance / modality / time horizon`
- 形成 viewpoint cluster

输出：

- `Thesis`
- thesis-to-statement links

### 5) ThesisMappingOperator

职责：

- 反向映射到：
  - papers
  - GitHub
  - HF assets
  - conference events
  - product releases
  - finance events
  - major news

输出：

- mapped evidence set
- contradiction candidates

### 6) InfluenceEvidencePacketCompiler

职责：

- 把 thesis 和支撑证据压缩成高模型输入包
- 构造 questions-for-high-model

输出：

- `InfluenceEvidencePacket`

### 7) InfluenceInsightCompiler

职责：

- 生成：
  - Influencer Insight Card
  - Thesis Brief
  - Cross-source Resonance Seed
  - AI Influence Topic
  - Deep Research Seed Pack
  - Open-source Project Brief
  - Finance / Event Watch
  - Action Queue

## 输出资产统一面

本模块最终至少产出 8 类标准资产：

- `Influencer Insight Card`
- `Thesis Brief`
- `Cross-source Resonance Seed`
- `AI Influence Topic`
- `Deep Research Seed Pack`
- `Open-source Project Brief`
- `Finance / Event Watch`
- `Action Queue`

这些资产是 Influence Source 向 Solar 其他系统暴露的标准件，不再用 ad-hoc 摘要替代。

## Quality Gate

社交内容必须强门禁。

### Statement Gate

required:

- source_url
- published_at
- influencer_id
- raw_text_or_transcript_span
- source_type

fail:

- no_source_url
- no_timestamp
- unverifiable_quote

### Transcript Gate

required:

- video_id
- timestamp_range
- language
- caption_type

fail:

- transcript_unavailable
- key_quote_not_locatable

### Thesis Gate

required:

- normalized_claim
- thesis_type
- topic
- modality
- time_horizon

fail:

- vague_claim
- no_actionable_topic
- pure_sentiment_without_thesis

### Evidence Mapping Gate

high-confidence 最低要求：

- social_source >= 1
- paper_or_code_source >= 1
- event_or_product_source >= 1

如果只有 social-only，则只允许低级归档，不允许进高结论。

### Compliance Gate

必须满足：

- use_public_or_authorized_sources_only
- respect_platform_terms
- do_not_bypass_access_controls
- separate_raw_quote_from_model_summary

## 三源共振接口合同

Social Signal Plane 作为 `Influence Source`，向共振层输出：

```text
thesis
viewpoint_cluster
resonance_seed
ai_influence_topic
deep_research_seed
open_project_brief
finance_event_watch
action_queue
```

与 `HF Paper Insight Flow` 对齐：

```text
thesis.topic            <-> paper method / benchmark / route tags
thesis.claim            <-> paper problem / contribution framing
speaker signals         <-> paper authors / labs / orgs
conference references   <-> accepted papers / keynote / workshop topics
```

与 `GitHub Hotspot Radar / Code Signal Plane` 对齐：

```text
thesis.topic            <-> repo topic tags / direction cluster
thesis.claim            <-> repo readme / release / issue keywords
viewpoint clusters      <-> GitHub direction clusters
cross-source resonance  <-> repo signals / project briefs / action queue
```

## 数据落盘结构

```text
raw/
  social_posts/
  video_transcripts/
  blog_posts/
  hn_threads/
  news_events/
  sec_filings/

extracted/
  influencer_profiles/
  statements/
  thesis/
  viewpoint_clusters/
  mapped_evidence_packets/
  resonance_seeds/
  topic_cards/
  project_briefs/

qmd/
  influencer_index.qmd
  thesis_index.qmd
  route_conflict_index.qmd
  resonance_index.qmd
  finance_event_index.qmd

graph/
  influence_graph
  thesis_graph
  viewpoint_graph
  resonance_graph
  action_graph
```

## 与现有线的合并策略

### 现有 social browser backend 线

`Tech Hotspot Radar: Social Browser Backend for X 大咖监控`

保留其价值，但降级为：

```text
Social Signal Plane 的 source collection slice
```

它只负责：

- account scan
- post collection
- browser fallback
- rate limit / cooldown
- social_posts 入库

它不再代表完整的社交洞察产品。

### 现有 YouTube transcript / ASR 线

保留其 caption / transcript / quality gate 价值，但定位为：

```text
Social Signal Plane 的 long-form statement evidence slice
```

它负责给 video / keynote / podcast statement 提供可审计 transcript，而不直接等同于洞察系统本身。

### 合并动作

1. 后续社交主线设计统一改用 `AI Influence Insight / Social Signal Plane`
2. `X / YouTube / Blog / HN / GDELT / SEC` 都被视为 source operator，不再各自长成独立产品名
3. Statement / Thesis / Evidence Packet / Resonance Seed 成为唯一事实模型
4. 所有 AI Influence 社交报告、Deep Research seed、项目机会输出都对齐本文资产面

## 分阶段实施建议

### Phase 1: 统一真相层

- influencer registry
- statement schema
- thesis schema
- evidence packet schema
- output asset schema

### Phase 2: 打穿 7 个 MVP operator

- seed registry
- collection
- normalization
- thesis extraction
- mapping
- packet compiler
- insight compiler

### Phase 3: 接三源共振

- 与 HF Paper 流打通
- 与 GitHub Hotspot Radar 打通
- resonance / contradiction / route shift 编排

### Phase 4: 重层能力

- finance / SEC / earnings 深度增强
- conference / keynote / agenda 强化
- viewpoint accuracy backtesting
- richer route-conflict graph

## 非目标

以下不是首批目标：

- 不把社交模块做成舆情产品
- 不把 engagement 排行榜当核心能力
- 不一开始就接满所有社交平台
- 不让高模型直接读取 raw post 列表
- 不把 X backend 采集线误当成完整洞察产品

## 后续执行建议

建议把 Influence 主线的 builder 入口压到 3 个大块：

```text
1. source + statement truth layer
2. thesis extraction + evidence mapping
3. insight compiler + resonance hooks
```

这样既能保留现有 X / YouTube / AI Influence 采集进度，也能把你现在这版更强的观点驱动研究发现系统变成唯一宪法。
