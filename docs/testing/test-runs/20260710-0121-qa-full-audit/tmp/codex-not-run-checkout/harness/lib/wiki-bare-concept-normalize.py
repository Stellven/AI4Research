#!/usr/bin/env python3
"""Normalize bare wiki targets by creating explicit concept/rule alias pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VAULT = Path.home() / "Knowledge"


PAGES: dict[str, dict[str, Any]] = {
    "concepts/ai基础设施能源瓶颈": {
        "title": "AI 基础设施能源瓶颈",
        "kind": "concept",
        "summary": "AI 训练、推理和数据中心扩张受电力、散热、资本开支和部署周期约束的系统性瓶颈。",
        "links": ["concepts/orbital-data-center", "references/lumen-orbit-why-train-ai-in-space-2024"],
    },
    "concepts/ai 基础设施能源瓶颈": {
        "title": "AI 基础设施能源瓶颈",
        "kind": "concept-alias",
        "summary": "带空格写法的别名页，指向 AI 基础设施能源瓶颈。",
        "links": ["concepts/ai基础设施能源瓶颈"],
    },
    "concepts/太阳同步轨道 sso": {
        "title": "太阳同步轨道 SSO",
        "kind": "concept",
        "summary": "太阳同步轨道是一类保持近似固定地方太阳时经过地表的轨道，常用于遥感，也被轨道数据中心设想引用。",
        "links": ["concepts/orbital-data-center", "references/lumen-orbit-why-train-ai-in-space-2024"],
    },
    "concepts/太阳同步轨道 (sso)": {
        "title": "太阳同步轨道 SSO",
        "kind": "concept-alias",
        "summary": "括号写法的别名页，指向太阳同步轨道 SSO。",
        "links": ["concepts/太阳同步轨道 sso"],
    },
    "concepts/可重用重型运载火箭": {
        "title": "可重用重型运载火箭",
        "kind": "concept",
        "summary": "降低大规模轨道基础设施部署成本的关键运输能力。",
        "links": ["concepts/orbital-data-center", "references/lumen-orbit-why-train-ai-in-space-2024"],
    },
    "concepts/被动辐射散热": {
        "title": "被动辐射散热",
        "kind": "concept",
        "summary": "通过辐射向冷空间排热的散热路径，是轨道数据中心设想中的关键热设计假设。",
        "links": ["concepts/orbital-data-center", "references/lumen-orbit-why-train-ai-in-space-2024"],
    },
    "concepts/轨道数据中心 (odc)": {
        "title": "轨道数据中心 ODC",
        "kind": "concept-alias",
        "summary": "Orbit Data Center 的别名页，连接轨道数据中心相关资料。",
        "links": ["concepts/orbital-data-center", "references/lumen-orbit-why-train-ai-in-space-2024"],
    },
    "concepts/kv cache分析与重定义": {
        "title": "KV Cache 分析与重定义",
        "kind": "concept",
        "summary": "把 KV cache 视为推理运行时状态、内存层次、压缩对象和跨模块 ABI 的综合分析框架。",
        "links": ["synthesis/kv-cache-as-computation-state-abi-verification-2026", "references/tpu-vs-gpu推理优势与计算相位演进", "references/残差流加速器可行性分析"],
    },
    "concepts/memory": {
        "title": "Memory",
        "kind": "concept",
        "summary": "智能体和模型系统中的长期记忆、工作记忆、上下文缓存和知识检索层。",
        "links": ["references/memory_system_architecture", "concepts/solar-data-ledger"],
    },
    "concepts/agent 评估": {
        "title": "Agent 评估",
        "kind": "concept",
        "summary": "对 agent 的任务完成质量、可观测性、工具使用、稳定性和可复用工作流进行评估。",
        "links": ["references/代理人工智能一年-从实际工作者身上学到的六个教训", "entities/solar-harness"],
    },
    "concepts/人机协作": {
        "title": "人机协作",
        "kind": "concept",
        "summary": "人类负责目标、反馈和验收，AI/agent 负责执行、整理和生成中间成果的协作模式。",
        "links": ["references/代理人工智能一年-从实际工作者身上学到的六个教训"],
    },
    "concepts/可复用 agent 平台": {
        "title": "可复用 Agent 平台",
        "kind": "concept",
        "summary": "把 agent 能力沉淀为可复用 runtime、工具、工作流和观测系统的平台化方向。",
        "links": ["references/代理人工智能一年-从实际工作者身上学到的六个教训", "references/solar-harness-runtime-skill-extraction-20260512"],
    },
    "concepts/可观测工作流": {
        "title": "可观测工作流",
        "kind": "concept",
        "summary": "能追踪输入、执行、状态、日志、交付物和验收证据的工作流。",
        "links": ["references/代理人工智能一年-从实际工作者身上学到的六个教训", "references/solar-data-plane-audit-cleanup-20260512"],
    },
    "concepts/工作流优先的 agent 设计": {
        "title": "工作流优先的 Agent 设计",
        "kind": "concept",
        "summary": "优先稳定任务流程、状态、工具和验收，再让模型在流程中发挥能力的 agent 设计方式。",
        "links": ["references/代理人工智能一年-从实际工作者身上学到的六个教训", "concepts/agent-cluster-paradigm"],
    },
    "concepts/energy-function-lyapunov": {
        "title": "Energy Function / Lyapunov",
        "kind": "concept",
        "summary": "用能量函数或 Lyapunov 函数描述系统稳定性、收敛和学习动态的理论工具。",
        "links": ["references/对谈田渊栋-ai走向何方-我们需要怎样的深度学习理论"],
    },
    "concepts/feature-learning": {
        "title": "Feature Learning",
        "kind": "concept",
        "summary": "模型自动学习可用于预测、控制或推理的表示特征。",
        "links": ["references/对谈田渊栋-ai走向何方-我们需要怎样的深度学习理论"],
    },
    "concepts/first-principles": {
        "title": "First Principles",
        "kind": "concept",
        "summary": "从基础约束、机制和可验证事实出发，而不是从表层类比出发的推理方式。",
        "links": ["references/对谈田渊栋-ai走向何方-我们需要怎样的深度学习理论", "rules/cortex-first"],
    },
    "concepts/grokking": {
        "title": "Grokking",
        "kind": "concept",
        "summary": "模型在长时间训练后突然从记忆化转向泛化的现象。",
        "links": ["references/对谈田渊栋-ai走向何方-我们需要怎样的深度学习理论"],
    },
    "concepts/neural-tangent-kernel": {
        "title": "Neural Tangent Kernel",
        "kind": "concept",
        "summary": "分析宽神经网络训练动态和泛化行为的一种理论框架。",
        "links": ["references/对谈田渊栋-ai走向何方-我们需要怎样的深度学习理论"],
    },
    "concepts/scaling-law": {
        "title": "Scaling Law",
        "kind": "concept",
        "summary": "描述模型性能随参数量、数据量、计算量等资源按规律变化的经验或理论关系。",
        "links": ["references/对谈田渊栋-ai走向何方-我们需要怎样的深度学习理论"],
    },
    "concepts/symmetry-breaking": {
        "title": "Symmetry Breaking",
        "kind": "concept",
        "summary": "系统从对称状态进入特定结构或功能分化状态的机制。",
        "links": ["references/对谈田渊栋-ai走向何方-我们需要怎样的深度学习理论"],
    },
    "concepts/causal-inference": {
        "title": "Causal Inference",
        "kind": "concept",
        "summary": "从观测、干预和结构假设中识别因果关系的推理方法。",
        "links": ["references/流形假设下的思考"],
    },
    "concepts/diffusion-models": {
        "title": "Diffusion Models",
        "kind": "concept",
        "summary": "通过逐步去噪或反向扩散生成数据的生成模型范式。",
        "links": ["references/流形假设下的思考"],
    },
    "concepts/geometric-deep-learning": {
        "title": "Geometric Deep Learning",
        "kind": "concept",
        "summary": "把几何结构、对称性和图/流形约束引入深度学习的研究方向。",
        "links": ["references/流形假设下的思考"],
    },
    "concepts/inductive-bias": {
        "title": "Inductive Bias",
        "kind": "concept",
        "summary": "学习系统在有限数据下偏向某类解的先验结构或约束。",
        "links": ["references/流形假设下的思考"],
    },
    "concepts/manifold-hypothesis": {
        "title": "Manifold Hypothesis",
        "kind": "concept",
        "summary": "高维数据通常集中在低维流形或近似低维结构上的假设。",
        "links": ["references/流形假设下的思考"],
    },
    "concepts/multi-modal-learning": {
        "title": "Multi-modal Learning",
        "kind": "concept",
        "summary": "跨文本、图像、音频、视频等多种模态学习统一表示或任务能力。",
        "links": ["references/流形假设下的思考"],
    },
    "concepts/natural-gradient": {
        "title": "Natural Gradient",
        "kind": "concept",
        "summary": "使用参数空间几何度量修正梯度方向的优化方法。",
        "links": ["references/流形假设下的思考"],
    },
    "concepts/offline-rl": {
        "title": "Offline Reinforcement Learning",
        "kind": "concept",
        "summary": "从固定历史数据集学习策略而不与环境在线交互的强化学习范式。",
        "links": ["references/流形假设下的思考"],
    },
    "concepts/reinforcement-learning": {
        "title": "Reinforcement Learning",
        "kind": "concept",
        "summary": "智能体通过动作、奖励和环境反馈学习策略的机器学习范式。",
        "links": ["references/流形假设下的思考", "synthesis/paper-collection-index-reasoning"],
    },
    "concepts/agent-architecture": {
        "title": "Agent Architecture",
        "kind": "concept",
        "summary": "agent 的模型、工具、记忆、规划、执行和反馈回路的系统结构。",
        "links": ["references/谷歌访谈纪要", "entities/solar-harness"],
    },
    "concepts/agi-strategy": {
        "title": "AGI Strategy",
        "kind": "concept",
        "summary": "围绕通用智能能力、产品化、基础设施和安全治理的长期路线判断。",
        "links": ["references/谷歌访谈纪要"],
    },
    "concepts/gemini": {
        "title": "Gemini",
        "kind": "concept",
        "summary": "Google 的多模态大模型系列，也常作为 Solar 多模型路由中的候选 worker。",
        "links": ["references/谷歌访谈纪要", "rules/solar-farm"],
    },
    "concepts/hallucination": {
        "title": "Hallucination",
        "kind": "concept",
        "summary": "模型生成不受证据支持或与事实不一致内容的错误模式。",
        "links": ["references/谷歌访谈纪要", "rules/cortex-first"],
    },
    "concepts/knowledge-graph-llm": {
        "title": "Knowledge Graph + LLM",
        "kind": "concept",
        "summary": "用知识图谱为 LLM 提供结构化记忆、实体关系和可追溯上下文。",
        "links": ["references/谷歌访谈纪要", "references/solar-kb-graph-debt-audit-20260512"],
    },
    "concepts/multimodal-inference": {
        "title": "Multimodal Inference",
        "kind": "concept",
        "summary": "跨模态输入进行理解、推理和生成的推理过程。",
        "links": ["references/谷歌访谈纪要", "synthesis/paper-collection-index-multimodal-llm"],
    },
    "concepts/token-economics": {
        "title": "Token Economics",
        "kind": "concept",
        "summary": "围绕 token 成本、上下文预算、模型路由和性价比的系统经济学。",
        "links": ["references/谷歌访谈纪要", "rules/solar-farm"],
    },
    "concepts/phase-state-machine": {
        "title": "Phase State Machine",
        "kind": "concept",
        "summary": "将复杂工作流拆成阶段和状态转换的控制模型。",
        "links": ["concepts/solar-workflow-phase-sequence-complexity", "entities/solar-harness"],
    },
    "concepts/solar-evo-self-evolution-architecture-design": {
        "title": "Solar Evo Self Evolution Architecture Design",
        "kind": "concept-alias",
        "summary": "Solar 自进化架构设计的别名页。",
        "links": ["concepts/solar-evo-self-evolution-architecture"],
    },
    "references/architecture-ml-intern-2026-04-28": {
        "title": "ML Intern Architecture 2026-04-28",
        "kind": "reference-alias",
        "summary": "ML intern 相关阶段性架构任务的别名页。",
        "links": ["references/solar-task-skin-classification-model-training-phase2"],
    },
    "synthesis/llm-api-pricing-landscape-2026": {
        "title": "LLM API Pricing Landscape 2026",
        "kind": "synthesis-alias",
        "summary": "LLM API 定价、Token SaaS 与平台竞争分析的综合索引页。",
        "links": ["synthesis/ai-token-saas-platform-war-us-china-competition-2026", "concepts/token-economics"],
    },
    "concepts/jeff dean：ai帕累托前沿与未来计算范式（精炼版）": {
        "title": "Jeff Dean: AI 帕累托前沿与未来计算范式",
        "kind": "concept",
        "summary": "关于 AI 计算效率、系统帕累托前沿和未来计算范式的访谈/观点索引。",
        "links": ["synthesis/kv-cache-as-computation-state-abi-verification-2026"],
    },
}


RULES: dict[str, dict[str, Any]] = {
    "rules/infrastructure-first-check": {
        "title": "Infrastructure First Check",
        "summary": "排查系统故障时先检查基础设施、运行时、进程、端口、数据库和索引，再判断上层逻辑。",
        "links": ["entities/solar-harness", "references/solar-data-plane-audit-cleanup-20260512"],
    },
    "rules/tvs-rendering": {
        "title": "TVS Rendering Rule",
        "summary": "TVS 渲染相关输出需要保留可观察、可复用、可验证的展示结构。",
        "links": ["references/solar-concept-progress-indicator"],
    },
    "rules/constraint-verification": {
        "title": "Constraint Verification Rule",
        "summary": "实现完成后必须用约束清单验证交付物，而不是只相信执行声明。",
        "links": ["references/solar-tool-capsule-validator", "rules/no-mock"],
    },
}


def render_page(rel: str, spec: dict[str, Any]) -> str:
    links = "\n".join(f"- [[{link}]]" for link in spec.get("links", []))
    return f"""---
title: "{spec['title']}"
category: {rel.split('/', 1)[0]}
tags: [bare-target-normalization, knowledge-graph-repair, {spec.get('kind', 'concept')}]
source: solar-harness
created: 2026-05-12
updated: 2026-05-12
lifecycle: graph-normalization
alias_for: {Path(rel).name}
---

# {spec['title']}

{spec['summary']}

## Graph Links

{links}

## Boundary

This page normalizes a historical bare wikilink target. It is intentionally
small and should be expanded only when new source evidence is available.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Create pages for bare broken wiki targets")
    parser.add_argument("--vault", default=str(VAULT))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    vault = Path(args.vault)
    specs = dict(PAGES)
    specs.update(RULES)
    planned = []
    for rel, spec in sorted(specs.items()):
        path = vault / f"{rel}.md"
        planned.append({"path": str(path), "rel": rel, "title": spec["title"]})
        if args.apply:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_page(rel, spec), encoding="utf-8")
    result = {"apply": args.apply, "count": len(planned), "planned": planned}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"apply={args.apply} count={len(planned)}")
        for item in planned:
            print(f"{item['rel']} -> {item['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
