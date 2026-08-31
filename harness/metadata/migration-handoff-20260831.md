# 最后一次 E2E 与开发迁移交接 — 2026-08-31

## 1. 当前结论

最后测试 **FAIL**，不是完整 E2E PASS。用户要求：本轮修复后只测试一次，遇到阻塞不再修复，直接准备迁移。本轮已遵守；下一位 agent 不得擅自恢复旧任务或继续修复。

- 分支：`codex/safety-before-intent-rollback-20260828`。
- 最后产品代码 commit：`f463b861bf47bddff46cc2ce3de151dcd8d78992`。
- Request：`final-contract-e2e-20260831-last`；session：`sprint-20260831-070119-intent-conduct-a-systematic-study-o-b9ff29b1`。
- 原 prompt 已纳入 Git：`harness/tests/fixtures/kv-cache-landscape-request.json`，task 字符串 SHA-256：`f8fd63b857f5c8f91ab64c7aa854b35313ecd1f3ad7a26bc2c132830da69e2e2`。
- 入口：锁定 backend 的 POST /intake，通过 tools/contract_smoke.py 提交；不是前端点击测试。rapid_smoke，一次提交，零人工干预。HTTP 200 / intake CLI 0 / 193.239 秒仅表示 intake 成功。

Intent 首轮通过。Requirement 使用共享合同 v2，首轮因过程要求选用了通用目标 check 被审查拒绝；运行时内置一次语义修复后通过，总计四次 Requirement 模型调用。Planner 决策为 generate，DAG 生成调用被模型接口拒绝。最终状态 failed/planning_failed；没有 SchedulerInput、冻结执行包、Scheduler、worker 或报告。

## 2. 当前未修复阻塞：Planner provider schema

确认证据：

- 实际发给模型的 `planning/semantic/generation-0/plan_call/model_output.schema.json`。
- `$defs/operator_requirements/properties` 中包含 cpu_cores_min、memory_mb_min、gpu_required，required 数组却不包含它们。
- 接口返回 HTTP 400 / invalid_json_schema，明确报告 Missing 'cpu_cores_min'，未生成 PlanIR。
- 对应源码：`harness/schemas/planning/plan-ir.semantic.structured.v2.schema.json`。
- 字段来自 `d62727cdcfb7fbf95bb94b7ca4dcd8ffdc22606c` 的资源合同补充。`harness/lib/intent_compiler.py::codex_compatible_schema` 当前没有处理这种可选属性与 provider 严格 schema 的差异。
- 同时出现的 bubblewrap PATH 警告称将使用 bundled fallback，不是本次 invalid_json_schema 的原因。

这是模型调用合同兼容性缺陷，不是 LLM 智力退化、旧 Requirement 输出、CPU 资源不足或服务容量错误。离线 JSON Schema 合法性检查没有覆盖 provider 的更窄约束。需要用户重新授权后，才可修正 Planner 的模型输出合同，并增加实际 provider-schema 边界的离线回归；不要以关闭校验或取消资源约束解决。也不要预先保证它是最后一个问题。

原始 run evidence 只在旧 runtime 的 .codex-tmp/final-contract-e2e-20260831-last/ 和对应 intents/sprints 下保留，不提交运行数据。此文和问题日志提供可迁移的最小故障证据。

## 3. 修复与迁移验证

| 检查 | 本轮证据 |
| --- | --- |
| Requirement 最终回归 | 46 passed，136.78 秒；实际调用 schema 枚举、模板权限、结构化 review、来源筛选 authority、预算和历史兼容 |
| Planner/Scheduler 回归 | 43 passed，130.87 秒；不能由此推断 provider 接受所有生成 schema |
| 迁移回归 | unittest test_migration*.py：13 passed，11.221 秒；文档更新后还会复验 |
| 合同闭包 | runtime + Git index：173 assets / 145 JSON Schemas；v1 合同保留，新 v2 合同已跟踪 |
| 全仓静态审计 | 5,326 tracked files；3,126 source files；2,245 Python 文件解析、141 个 runtime shell 语法检查无失败。35 个个人路径模式和 29 个旧地址模式命中，需要按已记录用途区分；不是 64 个已证实的主流程错误 |
| 传输安全范围 | 基于本地 remote-tracking refs 的 outgoing 扫描：703 objects / 262 blobs，无所测 token/private-key 模式命中。remote-tracking refs 未 fetch，扫描不等于完整保密认证 |

新补丁不存在生产代码的机器路径/项目标题硬编码。本轮新增代码、测试、合同均已进入 Git；修复前的 runtime/source 最小补丁逐文件核对，合同资产完整。此结论不包含历史未注册模块或可选工具的全面移植。

旧机器最终状态：backend PID 601，Coordinator PID 920 空闲，task workers 无；cwd、HARNESS_DIR、SOLAR_HARNESS_DIR 均为 /mnt/d/demo only version/harness；backend 仍为 http://172.19.127.84:8767/；52 sessions，其中原 51 个 ID 和状态文件均保留不变。E2E 期间 1,292 个受监视 source/schema/tool 哈希未改变。没有重启、替换 runtime、手改运行产物或旧任务复活。

## 4. 新机器依赖与仍存在的限制

项目目的、完整 pipeline、各阶段 schema 地址以 [NEW-MACHINE-START-HERE.md](NEW-MACHINE-START-HERE.md) 为入口。新合同机制见 [semantic-retrieval-contract.md](semantic-retrieval-contract.md)，逐条问题/修复/测试见 [pre-scheduler-stabilization-log-20260829.md](pre-scheduler-stabilization-log-20260829.md)。

1. 保留完整 Git checkout：harness、仓库根 requirements、tools 和 .agents/skills 都需要。不能只拷贝 harness 或旧 venv。
2. 主路径为 Linux/WSL2、Python 3.11+（已测 3.12.3）、Bash、Git、tmux、jq。运行依赖在 requirements/harness.txt；开发快照在 requirements/autosci-solar-native-dev.txt，后者不是全平台锁文件。本轮 pytest 为 9.1.1；上述新回归需要 pytest。jsonschema 4.26.0、referencing 0.37.0 为本轮已测版本，不代表所有旧版本通过。
3. 新机器独立安装/认证模型 CLI，验证服务进程的 PATH，而不只验证交互 shell。旧 backend 能找到已安装 codex，但当前普通 WSL shell PATH 找不到。认证、API key、个人配置不进入 Git 或迁移 prompt。
4. 当前 WSL PATH 没有 Linux Node，npm 指向 Windows 安装；不要复用这种混合环境。按前端 lockfile 在同一 Linux 环境配置 Node/npm，重新 npm ci/typecheck/build。此次未重建 UI，也未执行新主机安装。系统 bwrap 亦未在 PATH；模型 CLI 本次使用 bundled fallback，新主机需核验隔离能力。
5. 旧的可选 capture/config/benchmark/health helper 仍有 8765 默认值或链接；部分 vault/历史脚本有个人路径。正式 intake 不得切换到它们。旧请求还通过已配置的 Knowledge integration 归档 raw intake；这是宿主配置，不是新主机默认目录。完整限制见 [portability-audit-20260830.md](portability-audit-20260830.md)。不能承诺“所有代码在任何新环境都没有问题”。

新机安装、认证、Linux 前端构建、唯一 backend readiness 和 E2E 均为 NOT_TESTED。先由用户确认唯一 runtime、数据目录、backend URL/端口，再审阅安装 dry-run。不要沿用旧 IP；不要自动启动旧任务。环境检查失败必须报告，不得靠换 runtime、端口、关闭校验绕过。

## 5. GitHub 与传输

发布前的 2026-08-31 只读 ls-remote 检查（以下旧 tip 不代表发布后的当前状态）：

- origin：https://github.com/Coconut-ch1ken/OpenSolar.git，迁移分支远端 tip 为 `4ca349bcecf4517fa4c98fdf3bcb6f823fc6c553`。
- stellven：https://github.com/Stellven/AI4Research.git，未发现同名迁移分支。
- 远端 tip 是当前 HEAD 的祖先；最后产品代码比该 tip 多 11 commits，另加迁移文档。用户随后明确授权推送此迁移分支、上传 ZIP Release 附件并更新 prompt；不涉及 openJiuwen-Solar 或其他发布分支。

GitHub 迁移入口为 https://github.com/Coconut-ch1ken/OpenSolar/releases/tag/migration-20260831 ，ZIP 附件为 https://github.com/Coconut-ch1ken/OpenSolar/releases/download/migration-20260831/OpenSolar-migration-20260831.zip 。发布标记为 prerelease 且不设为 Latest：这是开发状态快照，最后 E2E 仍为 FAIL，不能当作稳定产品版本。

新机器首选直接 clone 指定迁移分支，核对发布 tag/manifest 的目标 commit 及已测产品 commit。发布后 clone 正确版本即可取得完整源码和最新 prompt，无需额外导入 bundle。ZIP 是可选备用交接包，包含本次目标 commit 的增量 bundle、manifest、prompt 和说明；它需要 GitHub 基线，不能独立 clone。新的 ZIP 不覆盖旧本地备份。传输成功与否以实际远端 ref、公开 Release 及下载哈希核验为准，而非文档中预先列出的 URL。

本地源仓库有无关 untracked 文件和旧临时 Git objects，均保留未删除；它们不是迁移依赖。增量 bundle 不含这些文件、旧 venv、session、备份和凭据。源码代码与审计摘要可迁移，运行历史若需要应另行私下授权转移。
