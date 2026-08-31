请接手 OpenSolar / AI4Research 的开发迁移。你没有本项目背景，请先完成迁移核验，不要立刻继续修代码或运行任务。

项目是本地优先的多智能体研究执行框架。默认链路是 GUI/CLI → LLM Intent Compiler → LLM Requirement Compiler → Elastic Planner → 冻结执行合同 → 确定性 Scheduler/Dispatcher → 研究算子 → 报告。不能退回按关键词分流或自由文本临时图。

代码分支必须保持 codex/safety-before-intent-rollback-20260828。最后产品代码 commit 是 f463b861bf47bddff46cc2ce3de151dcd8d78992，迁移包的目标 HEAD 还包含之后的交接文档 commit，以随包 transfer-manifest.json 为准。GitHub 仓库为 https://github.com/Coconut-ch1ken/OpenSolar.git；2026-08-31 核对该分支远端只有 4ca349bcecf4517fa4c98fdf3bcb6f823fc6c553，不能假定 clone 后已经有最新修复。

如果提供了 OpenSolar-final-migration-20260831.bundle，它是增量包，不是可单独 clone 的完整仓库。先核验 manifest 的 SHA-256、基线和目标 commit。在用户确认的新空目录 clone 指定 GitHub 分支，确认基线对象存在，再运行 git bundle verify。报告导入方案并获得用户允许，才从 bundle 导入并将这个新 checkout 快进至 manifest 目标；不得覆盖/重置已有 checkout、改分支或强推。如果该分支后来已被授权推送，直接核对其目标 commit 和 ancestry。不要复制旧 venv、node_modules、个人配置或凭据。

拿到完整目标代码后，按顺序阅读：
1. AGENTS.md、README.md。
2. harness/metadata/NEW-MACHINE-START-HERE.md。
3. harness/metadata/migration-handoff-20260831.md 和 semantic-retrieval-contract.md。
4. harness/metadata/README.md、pre-scheduler-stabilization-log-20260829.md。
5. requirements/harness.txt、requirements/autosci-solar-native-dev.txt、前端 package-lock 及 docs/WINDOWS.md。

最后一次原 prompt rapid 无干预 E2E 已结束为 FAIL：Intent 通过；Requirement 合同 v2 经一次内置语义修复后通过；Planner 决策 generate，但 DAG 模型调用返回 invalid_json_schema。具体是 schemas/planning/plan-ir.semantic.structured.v2.schema.json 的 operator_requirements 中 cpu_cores_min、memory_mb_min、gpu_required 没有进入 required，而 provider 不接受。lib/intent_compiler.py::codex_compatible_schema 未处理此差异。没有 Scheduler 或最终报告。用户要求遇到这个阻塞后停止修复并准备迁移；你不得擅自重试或修复。先解释故障与拟议方案，等用户明确授权。不要称之为模型变笨、资源不足或旧 Requirement 输出。

本轮修复已提交，涉及冻结 registry/Intent ID 枚举、selection_authority、独立 runtime policy、结构化 reviewer 缺陷和有界结构/语义修复。旧 v1 合同仍保留。离线 89 项回归通过不等于 provider/E2E 成功。迁移资产 173 个、有效 JSON Schema 145 个；全仓静态扫描仍有可选工具旧端口/个人路径及宿主配置限制，见文档，不要宣称全平台无环境问题。

首先请用户确认新机器唯一 runtime 根目录、数据目录、backend URL 和端口；不要沿用旧机器 IP，也不要自行新建额外 runtime、选择默认端口或 Electron 内嵌 backend。旧机器 D:\demo only version\harness / 172.19.127.84:8767 仅是历史身份，不是新机器的默认配置。安装前审阅 dry-run，确认 hooks/MCP 等个人配置修改范围。模型认证在本机安全配置，禁止打印/提交密钥。Windows 用 WSL2；需同环境 Linux Node/npm，不能混用 Windows npm。服务 PATH 也必须能找到模型 CLI。

在用户批准的 runtime 运行离线 import、合同闭包、回归和前端构建；不要先启动 Coordinator/workers。核验实际 cwd、HARNESS_DIR、SOLAR_HARNESS_DIR、监听端口、URL、Git 分支/commit、session 数和 worker 状态。不一致就停止。新主机安装/E2E 在实际验证前都是 NOT_TESTED。

未来每次修复：runtime-first 最小补丁；编辑前记录 SHA-256 并备份；不手改/删除 session、运行数据、历史日志和备份；等价最小补丁同步 Git，新增源码/测试必须跟踪，追加问题/修复日志，正常 commit。未经授权不 pull/merge/rebase/reset/push，不恢复旧任务。若用户之后授权 E2E，原请求 fixture 是 harness/tests/fixtures/kv-cache-landscape-request.json；使用受信任 rapid_smoke 环境，不是 prompt 关键词；无干预运行，首个阻塞停止报告。

现在先给我一个简短核验报告：拿到的 commit、资料完整性、环境缺口、需要我确认的新 runtime/backend 值；不要开始修复 Planner。
