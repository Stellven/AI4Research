from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SPRINT_ID = "sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s03-core-runtime"
EPIC_ID = "epic-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究"
NODE_IDS = (
    "C1_schema_storage_state",
    "C2_collection_canonical_enrichment",
    "C3_taxonomy_scoring_packet",
    "C4_reasoning_compiler_store_watch",
    "C5_core_runtime_release",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_design_markdown() -> str:
    return f"""# Design: HF Paper Insight Flow Core Runtime

epic_id: `{EPIC_ID}`
sprint_id: `{SPRINT_ID}`
slice: `core-runtime`
status: planning_complete
generated_at: {_now()}
upstream: S02 architecture passed (10 层 / 6 数据对象 / 5 决策 / 5 OQ)
downstream: S04 orchestration-ui · S05 verification-release

## 目标

把 S02 架构切片收敛成可实现的核心 runtime：schema、持久化、状态机、provider enrichment、taxonomy/scoring/packet、reasoning route、compiler/store/watch，以及与旧 wake/dispatch/status 的兼容层。

## 模块边界

- `harness/lib/hf_paper_insight/schema.py`: `PaperSnapshot` / `PaperCanonical` / `PaperEnrichment` / `PaperTaxonomy` / `PaperSignal` / `PaperEvidencePacketV2`
- `harness/lib/hf_paper_insight/storage.py`: SQLite WAL + JSON 字段存储、raw/extracted 索引、fallback file buffer
- `harness/lib/hf_paper_insight/state_machine.py`: snapshot -> canonical -> enrich -> classify -> score -> packet -> resonance -> compile -> store -> watch
- `harness/lib/hf_paper_insight/providers/`: HF / arXiv / HF assets / Semantic Scholar / GitHub enrichment adapter
- `harness/lib/hf_paper_insight/scoring.py`: 4 组主分数、36 权重 profile、signal_class、R0-R5 resonance
- `harness/lib/hf_paper_insight/reasoning.py`: Browser Agent high-reasoning route contract + gated packet dispatch
- `harness/lib/hf_paper_insight/compiler.py`: report/cards/seeds/topics/experiments/projects/deep-research compiler
- `harness/lib/hf_paper_insight/knowledge_store.py`: raw/extracted/QMD/graph write orchestration + repair hook
- `harness/lib/hf_paper_insight/watch.py`: sustained resonance / delta trigger / watch spec
- `harness/lib/hf_paper_insight/compat.py`: legacy wake/dispatch/status compatibility adapter

## 关键实现决策

- D1: 默认存储层用 SQLite WAL + JSON 字段，保留迁往 PostgreSQL 的 seam，不在本切片引入数据库迁移器。
- D2: provider 限流采用 per-provider breaker + exponential backoff，不做共享 throttle。
- D3: high reasoning 复用既有 Browser Agent 路径，只实现 gated packet routing contract 和 fallback。
- D4: 权重存储用 YAML profile + hardcoded fallback，运行时支持 reload，不允许权重硬散在调用点。
- D5: `raw` 同步落盘，`extracted/QMD/graph` 异步 fan-out，失败进入 fallback file queue 与 repair hook。

## 运行时切面

- control plane: CLI profile/config、threshold、override、watch trigger、status projection
- data plane: snapshot -> canonical -> enrichment -> taxonomy -> scoring -> packet -> resonance -> compile -> store
- compatibility plane: 不破坏现有 wake/dispatch/status；状态可从 metadata/events 重建

## 风险与非目标

- 本切片不实现 orchestration-ui，不改 status-server UI 细节
- 不直接跑真实 Browser Agent high reasoning 请求
- 不把 YouTube 低质量 transcript 作为强证据
- 不把 HF ranking 当结论，只当 attention signal
"""


def build_plan_markdown() -> str:
    return f"""# Plan: HF Paper Insight Flow Core Runtime

gate: `{SPRINT_ID}:passed`
knowledge_context: solar-harness context inject used
upstream: S02 architecture / data_models / interfaces / OQ resolutions / traceability
downstream: S04 orchestration-ui · S05 verification-release

## DAG

```text
C1_schema_storage_state
  ├─→ C2_collection_canonical_enrichment ┐
  └─→ C3_taxonomy_scoring_packet          ├─→ C4_reasoning_compiler_store_watch ─→ C5_core_runtime_release
```

## 节点验收

| 节点 | 核心验收 |
|------|----------|
| `C1` | 6 核心实体 schema、SQLite WAL 持久化 contract、runtime state rebuild seam、兼容层基线 |
| `C2` | daily/weekly/monthly snapshot、canonical identity、HF/arXiv/HF assets enrichment adapter、provider rate-limit/backoff |
| `C3` | taxonomy、4 类主分数、36 权重 profile、Packet Gate、signal_class、R0-R5 resonance |
| `C4` | Browser Agent gated reasoning contract、compiler 七类产物、knowledge raw/extracted/QMD/graph fan-out、watch trigger |
| `C5` | 单测、最小回归、compat 验证、handoff、traceability、builder 可复查证据 |

## Stop Rules

- 缺 task_graph.json 不得派 builder
- 缺可复现验证不得标记 passed
- 不破坏既有 wake/dispatch/status
- 不把 raw paper list 直接送高模型
- 不放宽 packet/insight/resonance gate
"""


def build_task_graph() -> dict[str, Any]:
    generated_at = _now()
    gate = f"{SPRINT_ID}:passed"
    return {
        "schema_version": "solar.task_graph.v1",
        "sprint_id": SPRINT_ID,
        "epic_id": EPIC_ID,
        "title": "HF Paper Insight Flow Core Runtime",
        "dag_variant": "standard",
        "generated_at": generated_at,
        "required_gates": [gate],
        "nodes": [
            {
                "id": "C1_schema_storage_state",
                "goal": "落地 6 核心实体 schema、SQLite WAL 持久化 contract、runtime state rebuild seam、compat adapter 边界。",
                "depends_on": [],
                "write_scope": [
                    "harness/lib/hf_paper_insight/schema.py",
                    "harness/lib/hf_paper_insight/storage.py",
                    "harness/lib/hf_paper_insight/state_machine.py",
                    "harness/lib/hf_paper_insight/compat.py",
                    "harness/tests/test_hf_paper_insight_schema.py",
                ],
                "read_scope": [
                    f"sprints/{SPRINT_ID}.prd.md",
                    f"sprints/{SPRINT_ID}.contract.md",
                    f"sprints/sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s02-architecture.architecture.md",
                    f"sprints/sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s02-architecture.data_models.md",
                    f"sprints/sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s02-architecture.interfaces.md",
                    f"sprints/sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s02-architecture.open_questions_resolutions.md",
                    f"sprints/sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s02-architecture.traceability.json",
                ],
                "required_capabilities": ["python", "state-machine", "testing"],
                "preferred_model": "sonnet",
                "acceptance": [
                    "核心 API 有单测覆盖",
                    "状态变更可由元数据或事件重建",
                ],
                "gate": gate,
            },
            {
                "id": "C2_collection_canonical_enrichment",
                "goal": "实现 snapshot / canonical / enrichment 基础运行时，含 HF/arXiv/HF assets 和 provider 限流退避。",
                "depends_on": ["C1_schema_storage_state"],
                "write_scope": [
                    "harness/lib/hf_paper_insight/providers/",
                    "harness/lib/hf_paper_insight/collector.py",
                    "harness/lib/hf_paper_insight/canonicalizer.py",
                    "harness/tests/test_hf_paper_insight_collection.py",
                ],
                "read_scope": [
                    f"sprints/{SPRINT_ID}.design.md",
                    f"sprints/{SPRINT_ID}.plan.md",
                    f"sprints/sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s02-architecture.data_models.md",
                ],
                "required_capabilities": ["python", "testing"],
                "preferred_model": "sonnet",
                "acceptance": [
                    "至少支持 HF metadata、arXiv metadata、HF linked assets enrichment",
                    "同一 arXiv/HF paper canonical identity 稳定",
                ],
                "gate": gate,
            },
            {
                "id": "C3_taxonomy_scoring_packet",
                "goal": "实现 taxonomy、36 权重 scoring、signal class、Packet Gate、R0-R5 resonance packet 基础。",
                "depends_on": ["C1_schema_storage_state"],
                "write_scope": [
                    "harness/lib/hf_paper_insight/taxonomy.py",
                    "harness/lib/hf_paper_insight/scoring.py",
                    "harness/lib/hf_paper_insight/packet.py",
                    "harness/tests/test_hf_paper_insight_scoring.py",
                ],
                "read_scope": [
                    f"sprints/{SPRINT_ID}.design.md",
                    f"sprints/{SPRINT_ID}.plan.md",
                    f"sprints/sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s02-architecture.interfaces.md",
                ],
                "required_capabilities": ["python", "testing"],
                "preferred_model": "sonnet",
                "acceptance": [
                    "输出 PaperTaxonomy 和 PaperSignal",
                    "只把通过 Packet Gate 的 packet 送 high reasoning route",
                ],
                "gate": gate,
            },
            {
                "id": "C4_reasoning_compiler_store_watch",
                "goal": "接 Browser Agent reasoning contract、compiler 七类资产、knowledge store fan-out、watch trigger。",
                "depends_on": ["C2_collection_canonical_enrichment", "C3_taxonomy_scoring_packet"],
                "write_scope": [
                    "harness/lib/hf_paper_insight/reasoning.py",
                    "harness/lib/hf_paper_insight/compiler.py",
                    "harness/lib/hf_paper_insight/knowledge_store.py",
                    "harness/lib/hf_paper_insight/watch.py",
                    "harness/tests/test_hf_paper_insight_runtime.py",
                ],
                "read_scope": [
                    f"sprints/{SPRINT_ID}.design.md",
                    f"sprints/{SPRINT_ID}.plan.md",
                    f"sprints/sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s02-architecture.handoff.md",
                ],
                "required_capabilities": ["python", "testing", "browser.browse"],
                "preferred_model": "sonnet",
                "acceptance": [
                    "生成 report/cards/seeds/topics/experiments/projects/deep-research 七类资产",
                    "产物写入 Knowledge raw/extracted，QMD 可搜索",
                ],
                "gate": gate,
            },
            {
                "id": "C5_core_runtime_release",
                "goal": "汇总 compat 回归、handoff、traceability、builder 证据，并准备给 S05 的验证面。",
                "depends_on": ["C4_reasoning_compiler_store_watch"],
                "write_scope": [
                    f"sprints/{SPRINT_ID}.handoff.md",
                    f"sprints/{SPRINT_ID}.traceability.json",
                    "harness/tests/",
                ],
                "read_scope": [
                    f"sprints/{SPRINT_ID}.design.md",
                    f"sprints/{SPRINT_ID}.plan.md",
                    f"sprints/{SPRINT_ID}.task_graph.json",
                ],
                "required_capabilities": ["python", "testing"],
                "preferred_model": "sonnet",
                "acceptance": [
                    "旧路径兼容，不破坏现有 wake/dispatch/status",
                    "用 2026-05-27 的 HF daily/weekly/monthly 数据跑通第一条完整闭环",
                ],
                "gate": gate,
            },
        ],
    }


def generate_planner_artifacts(runtime_root: Path) -> dict[str, Any]:
    sprint_root = runtime_root / "sprints"
    design_path = sprint_root / f"{SPRINT_ID}.design.md"
    plan_path = sprint_root / f"{SPRINT_ID}.plan.md"
    graph_path = sprint_root / f"{SPRINT_ID}.task_graph.json"
    status_path = sprint_root / f"{SPRINT_ID}.status.json"

    design = _write_text(design_path, build_design_markdown())
    plan = _write_text(plan_path, build_plan_markdown())
    graph = build_task_graph()
    _write_json(graph_path, graph)

    from graph_scheduler import validate_graph  # noqa: WPS433
    from runtime_status import transition_status  # noqa: WPS433

    validation = validate_graph(graph)
    if not validation.get("ok"):
        return {
            "ok": False,
            "sprint_id": SPRINT_ID,
            "reason": "invalid_task_graph",
            "validation": validation,
        }

    updated, message = transition_status(
        status_path,
        "active",
        "hf_s03_core_runtime_planning_complete",
        "hf_s03_core_runtime_planner",
        extra={
            "graph_path": str(graph_path),
            "design_md": str(design),
            "plan_md": str(plan),
            "route_role": "builder_main",
            "reason": "planner_artifacts_and_task_graph_ready",
            "status_fields": {
                "phase": "planning_complete",
                "stage": "planning_complete",
                "handoff_to": "builder_main",
                "target_role": "builder_main",
                "task_graph_status": "active",
            },
        },
    )
    return {
        "ok": True,
        "sprint_id": SPRINT_ID,
        "design_md": str(design),
        "plan_md": str(plan),
        "task_graph_json": str(graph_path),
        "validation": validation,
        "status": updated,
        "message": message,
    }
