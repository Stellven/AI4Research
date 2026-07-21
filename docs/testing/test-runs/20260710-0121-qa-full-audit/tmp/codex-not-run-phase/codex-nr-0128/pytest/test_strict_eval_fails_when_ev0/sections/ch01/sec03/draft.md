# 问题定义与研究边界：证据链与代表工作

## Research Question

latent reasoning 在“问题定义与研究边界/证据链与代表工作”上的证据、架构取舍和争议是什么？

## Position

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 以 evidence pack 为事实源，目标不是堆材料，而是围绕 机制分层、状态表示、系统边界和可复现实现路径 建立可审计的 survey 论证；本节先限定 `architecture` 问题边界，再比较证据强度、工程代价、评价可信度和开放争议。当前证据包包含来源类型 `benchmark, code, official_doc, paper`，其中 `benchmark` 只能支持其直接覆盖的结论，不能替代跨章节 synthesis。 [claim:cl_0] [evidence:ev_0]

## Claim Map

1. ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 claim-slot-1 turns 'latent reasoning architecture requires evaluation evidence' into a bounded architecture claim instead of a generic survey assertion. [claim:cl_0] [evidence:ev_0]
2. ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 claim-slot-2 turns 'latent reasoning architecture requires evaluation evidence' into a bounded architecture claim instead of a generic survey assertion. [claim:cl_1] [evidence:ev_1]
3. ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 claim-slot-3 turns 'latent reasoning architecture requires evaluation evidence' into a bounded architecture claim instead of a generic survey assertion. [claim:cl_2] [evidence:ev_2]
4. ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 claim-slot-4 turns 'latent reasoning architecture requires evaluation evidence' into a bounded architecture claim instead of a generic survey assertion. [claim:cl_3] [evidence:ev_3]
5. ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 claim-slot-5 turns 'latent reasoning architecture requires evaluation evidence' into a bounded architecture claim instead of a generic survey assertion. [claim:cl_4] [evidence:ev_4]
6. ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 claim-slot-6 turns 'latent reasoning architecture requires evaluation evidence' into a bounded architecture claim instead of a generic survey assertion. [claim:cl_5] [evidence:ev_5]

## Evidence Map

- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 evidence-slot-1: ev_0 / paper supports 机制分层、状态表示、系统边界和可复现实现路径 with span summary 'latent reasoning architecture evaluation deployment'. [evidence:ev_0]
- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 evidence-slot-2: ev_1 / paper supports 机制分层、状态表示、系统边界和可复现实现路径 with span summary 'latent reasoning architecture evaluation deployment'. [evidence:ev_1]
- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 evidence-slot-3: ev_2 / paper supports 机制分层、状态表示、系统边界和可复现实现路径 with span summary 'latent reasoning architecture evaluation deployment'. [evidence:ev_2]
- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 evidence-slot-4: ev_3 / paper supports 机制分层、状态表示、系统边界和可复现实现路径 with span summary 'latent reasoning architecture evaluation deployment'. [evidence:ev_3]
- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 evidence-slot-5: ev_4 / official_doc supports 机制分层、状态表示、系统边界和可复现实现路径 with span summary 'latent reasoning architecture evaluation deployment'. [evidence:ev_4]
- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 evidence-slot-6: ev_5 / code supports 机制分层、状态表示、系统边界和可复现实现路径 with span summary 'latent reasoning architecture evaluation deployment'. [evidence:ev_5]
- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 evidence-slot-7: ev_6 / benchmark supports 机制分层、状态表示、系统边界和可复现实现路径 with span summary 'latent reasoning architecture evaluation deployment'. [evidence:ev_6]

## Source Map

- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 source-slot-1: src_0: paper / Latent Reasoning Paper
- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 source-slot-2: src_1: paper / Continuous Thought Paper
- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 source-slot-3: src_2: paper / Reasoning Survey Proceedings
- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 source-slot-4: src_3: paper / Neural Computation Journal Article
- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 source-slot-5: src_4: official_doc / Official Developer Docs
- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 source-slot-6: src_5: code / Latent Reasoning Repository
- ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 source-slot-7: src_6: benchmark / Latent Reasoning Benchmark

## Literature Lineage

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 的 literature lineage 不按来源顺序机械拼接，而是把显式 chain-of-thought 基线、continuous thought 过渡、hidden-state deliberation、Coconut-style latent reasoning 和生产可审计混合系统放到一条可批判的演进线上。论文证据负责机制与实验假设，代码证据负责可复现路径，benchmark 证据负责评价协议，official_doc 负责部署边界。 [claim:cl_0] [evidence:ev_0]

## Method Taxonomy

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 的 method taxonomy 按四个轴拆分：representation 轴区分 token、continuous state 与 hidden state；control policy 轴区分固定步数、adaptive deliberation 与 verifier-coupled search；supervision 轴区分 imitation、RL、self-training 与 synthetic traces；observability 轴区分可审计 token trace、弱可解释 latent trajectory 与黑箱内部状态。 [claim:cl_0] [evidence:ev_0]

## Architecture Synthesis

在 ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 中，架构 synthesis 先拆成机制层、系统层和评价层：机制层解释 机制分层、状态表示、系统边界和可复现实现路径 为什么可能成立，系统层检查它如何被实现、调度、复现和迁移，评价层判断现有 `benchmark, code, official_doc, paper` 是否足以支撑本节结论。三层必须保持分离，否则 `architecture` 主题会把概念说明、经验判断和工程结论混成看似深入但不可审计的叙述。 [claim:cl_0] [evidence:ev_0]

## Comparative Positioning

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 的 comparative positioning 不把所有引用压成同一权重：`benchmark` 提供本节主证据，`code` 用来检查外推边界，其余来源只补充实现、评价或部署侧信息。若某一来源类型缺失，本节结论必须降级为局部判断；只有多类来源围绕 机制分层、状态表示、系统边界和可复现实现路径 相互支撑时，才可以进入章节级 survey 判断。 [claim:cl_0] [evidence:ev_0]

## Terminology Evolution

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 tracks the terminology path from chain-of-thought and explicit reasoning chains toward continuous thought, hidden-state deliberation, Coconut-style latent reasoning, and auditable hybrid systems. [claim:cl_0] [evidence:ev_0]

## Evaluation Protocol Matrix

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 的 evaluation protocol matrix 至少比较五列：task family 是否覆盖长程推理，baseline/ablation 是否公平，metric 是否区分准确率、成本与可审计性，reproducibility 是否能由代码或数据卡复核，deployment transfer 是否会引入观测性和回滚成本。缺任一列时，本节结论必须降级。 [claim:cl_1] [evidence:ev_1]

## Evaluation And Risk Boundary

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 的 evaluation boundary 必须说明数据集、任务形态、指标口径和外推边界，并把 `把机制可行性误读为工程可控性` 标为主要降级风险。若证据来自论文，应检查实验设置和 baseline；若证据来自代码，应检查可运行性、维护状态和实现约束；若证据来自 benchmark，应检查任务覆盖和指标是否与本节 `architecture` 场景一致。 [claim:cl_1] [evidence:ev_1]

## Limitations And Failure Modes

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 必须把 failure modes 写在正文中：机制分层、状态表示、系统边界和可复现实现路径 可能只在短任务、单模型、单 benchmark 或不可复现实验中成立，代码证据可能缺少生产约束，官方文档也可能只描述支持路径而不覆盖失败路径。因此，本节结论需要标注适用条件、不可外推区域和后续 evidence miner 必须补齐的缺口。 [claim:cl_1] [evidence:ev_1]

## Controversy Matrix

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 的 controversy matrix 分成支持证据、负面证据、baseline 争议、interpretability 争议和 deployment-risk 争议五栏。若 `benchmark` 与 `code` 在任务规模、实现假设或评价口径上冲突，本节必须把冲突保留为争议项，而不是在 narrative synthesis 中抹平。 [claim:cl_2] [evidence:ev_2]

## Contradiction Slots

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 保留三个反证槽位：第一，`benchmark` 证据可能只覆盖 机制分层、状态表示、系统边界和可复现实现路径 的局部任务；第二，`code` 与主来源之间可能存在时间差、实现差或评价口径差；第三，`把机制可行性误读为工程可控性` 可能没有被现有 benchmark 捕捉。后续 chapter synthesis 必须消费这些槽位，不能只保留支持性证据。 [claim:cl_2] [evidence:ev_2]

## Revision: Architecture And Evaluation Detail

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 的本轮修订围绕 机制分层、状态表示、系统边界和可复现实现路径 展开，而不是复述通用写作模板；`benchmark, code, official_doc, paper` 证据被拆成主来源 `benchmark` 与校验来源 `code`，前者限定论证入口，后者校准评价或工程边界。该节结论必须显式标注 `把机制可行性误读为工程可控性` 这一降级条件，避免把局部实验直接升级为通用规律。 [claim:cl_0] [evidence:ev_0]

## Revision: Terminology Evolution And Academic Survey Frame

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 将术语演进显式写入正文：chain-of-thought 或显式推理链强调 token-level narration，continuous thought 强调连续隐变量计算，hidden-state deliberation 强调内部状态迁移，Coconut-style latent reasoning 则把这些机制放入可训练和可评估的架构 taxonomy。教授级 survey 必须同时记录 baseline、ablation、evaluation protocol、reproducibility、deployment 和 auditability，否则长文只是材料堆叠。 [claim:cl_0] [evidence:ev_0]

## Open Problems

ch01#3::ch01/sec03::问题定义与研究边界：证据链与代表工作 的开放问题不是通用 future-work 列表，而是要求下一轮围绕 机制分层、状态表示、系统边界和可复现实现路径 补充反证来源、统一 `architecture` 术语、复核 `benchmark` 与 `code` 的可比性，并量化 `把机制可行性误读为工程可控性` 对章节结论的影响。该节最终版本应把这些问题映射回 claim_id 和 evidence_id，而不是依赖模型自由发挥。
