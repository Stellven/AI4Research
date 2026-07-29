# Prompt：实现 Phase 22 真实任务测试代码

你现在接手 OpenSolar Phase 22 的真实任务（journey）测试代码实现。

仓库：`C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical`

## 目标

根据以下已经批准的任务计划，为 10 个真实任务编写可执行测试代码：

`tests/journeys/phase22/journey-test-plan.md`

这些测试的目的不是重新逐项证明 1,502 个 atomic feature，而是实际调用产品公开入口，让 OpenSolar 完成一件有用的事情，并保存足以让人判断结果的证据。

## 开始前必须完成

1. 完整阅读仓库根目录 `AGENTS.md`。
2. 完整阅读 `tests/journeys/phase22/journey-test-plan.md`。
3. 阅读 `README.md` 的 Quick Start、Basic Workflow、Platform Support 和 AutoSci Commands。
4. 阅读 `tests/README.md`，检查 `git status --short`，保护现有 dirty-worktree 改动。
5. 检查每个 journey 实际使用的产品入口、现有集成测试和输出 schema。任务计划定义用户目标与通过边界，但不能代替你核对当前命令语法。

## 你的文件所有权

你可以新增或修改：

- `tests/journeys/phase22/code/`
- `tests/journeys/phase22/fixtures/`
- `.codex-tmp/phase22-worker-results/journey-code-batch-001/result.json`

运行时证据写入：

- `outputs/phase22-real-journeys/<run-id>/`

除非为导入修复测试目录内的代码，否则不要编辑其他路径。尤其不得编辑或重新生成：

- `AGENTS.md`
- `tests/journeys/phase22/journey-test-plan.md`
- `tests/platform/phase22/atomic_feature_matrix.json`
- `tests/platform/phase22/atomic_feature_matrix_overrides.json`
- `docs/integrations/autosci/phase-22-test-report.xlsx`
- `docs/integrations/autosci/phase-22-progress-log.md`
- brief workbook

不要修改生产代码来让 journey 通过。发现产品 bug 时保留真实失败证据，写入结果文件；不要顺手修产品。

## 推荐代码结构

使用 Python/pytest 作为统一 orchestration 层，但通过 subprocess、HTTP 或真实 CLI 调用产品公开入口，而不是直接调用内部函数伪造端到端成功：

- `tests/journeys/phase22/code/conftest.py`
- `tests/journeys/phase22/code/journey_runner.py`
- `tests/journeys/phase22/code/evidence.py`
- `tests/journeys/phase22/code/test_j01_install_status.py`
- `tests/journeys/phase22/code/test_j02_live_coding_task.py`
- `tests/journeys/phase22/code/test_j03_platform_benchmark.py`
- `tests/journeys/phase22/code/test_j04_paper_ingestion.py`
- `tests/journeys/phase22/code/test_j05_literature_discovery.py`
- `tests/journeys/phase22/code/test_j06_idea_generation.py`
- `tests/journeys/phase22/code/test_j07_experiment_lifecycle.py`
- `tests/journeys/phase22/code/test_j08_claim_verification.py`
- `tests/journeys/phase22/code/test_j09_report_delivery.py`
- `tests/journeys/phase22/code/test_j10_backup_restore_uninstall.py`
- `tests/journeys/phase22/code/README.md`

可以根据实际需要调整文件名，但必须保持“一眼能看出 journey ID 和用途”。共享 helper 不得包含复制产品逻辑的替代实现。

## 实现要求

### 1. 每个 journey 都必须有可执行入口

十个任务都要能被单独选择和运行。测试名称包含 `p22_j01` 至 `p22_j10`。提供：

- 一条运行全部无需 live provider 的命令；
- 每个 journey 的单独 pytest selector；
- 一条只运行 network/live-provider journeys 的命令；
- 必要环境变量和系统依赖说明。

### 2. 测试必须真正走产品入口

优先调用：

- `install.sh`、`bin/solar`；
- `harness/solar-harness.sh`；
- `solar harness ...` / AutoSci skill shim 的真实产品分发入口；
- status server 的真实 loopback HTTP endpoint；
- 实际本地 Python experiment subprocess。

不得用以下方式制造 PASS：

- 只检查文件或 symbol 存在；
- 搜索生产源代码文本；
- 在测试里重写产品算法并验证自己的副本；
- 直接复制现有成功 fixture 作为“真实执行结果”；
- 接受“成功或失败都可以”的宽松断言；
- 用 mock 替代 journey 要证明的主要产品行为。

允许使用受控 fixture 作为用户输入，也允许 fake 掉非目标外部副作用，但必须保留 journey 的核心真实路径。例如 P22-J07 可以生成小型 CSV 和脚本，但必须真的启动实验进程；P22-J05 不得用内置候选假装实时文献搜索。

### 3. 安全隔离

- 每次运行创建唯一 sandbox `HOME`、`SOLAR_HOME`、`CLAUDE_DIR`、`HARNESS_DIR` 和动态端口。
- 不得读取、写入、卸载或删除真实用户 home 中的 Solar、Claude、Codex 或研究资料。
- 不得硬编码 `/tmp`；使用 `tmp_path`/平台安全路径。
- 所有 daemon、status server、tmux session 和子进程必须在 teardown 中停止，即使断言失败也不能遗留。
- P22-J10 只能操作经过绝对路径校验、位于本次 sandbox 的目录。
- 不打印、存档或提交 API key、`.env` 内容。日志环境变量必须经过 allowlist/redaction。

### 4. 结果状态必须诚实

仅使用计划中的状态：

- `PASS`
- `PASS_WITH_KNOWN_LIMITATIONS`
- `FAIL`
- `ENVIRONMENT_BLOCKED`
- `NOT_AVAILABLE`
- `NOT_TESTED`

规则：

- 断言到达且产品行为不满足通过标准：`FAIL`。
- 测试代码、fixture、路径、端口或 recorder 自己出错：先修测试再重跑，不能标成环境阻塞。
- 缺少明确的 tmux、OS、network、credential、account 或 live provider：`ENVIRONMENT_BLOCKED`，并写出确切需求和重跑命令。
- 当前代码没有产品入口或必要行为：`NOT_AVAILABLE`，要引用查过的最接近入口和缺失内容。
- 有用核心结果完成但存在计划允许的明确边界：`PASS_WITH_KNOWN_LIMITATIONS`；限制必须写进证据，不能用它掩盖核心失败。
- pytest skip 之前也要生成 journey manifest，记录 blocker；不要让 skip 成为无解释的黑洞。

### 5. 每次运行保存统一证据

每个 `outputs/phase22-real-journeys/<run-id>/` 至少包含：

- `journey-result.json`
- `commands.json`
- `stdout/` 与 `stderr/`
- `artifacts.json`
- `assertions.json`
- `limitations.md`

`journey-result.json` 至少记录：

- `schema_version`
- `journey_id`、名称和执行 selector
- `started_at`、`finished_at`、duration
- `repo_head`（使用 `git rev-parse HEAD`）
- OS/WSL、Python、bash、tmux、selected runtime/provider 信息
- 使用的 sandbox 路径（不得含 secret）
- 每条真实命令、退出码和超时状态
- 核心产物相对路径及 SHA-256
- 通过标准逐条结果
- 实际观察到的 L2 和对应 evidence path
- 最终状态、限制、blocker 和重跑命令

在 `.codex-tmp/phase22-worker-results/journey-code-batch-001/result.json` 汇总十项结果、selector、执行命令和证据目录。这个 worker result 只供 integration owner 后续同步，不直接修改 workbook。

### 6. Provider 与网络边界

- P22-J01、J03、J04、J07、J08、J10 应优先做到本地可运行。
- P22-J05、J06、J09 可以需要 network/model；无相应环境时实现测试但记录 `ENVIRONMENT_BLOCKED`。
- P22-J02 必须有真实选定 runtime 的证据才可 PASS；没有明确 live-provider 授权时不要发起调用。
- 不要自动读取或打印 `.env`。只能使用运行环境中已经提供给测试进程的必要变量，并在日志中只记录“present/absent”。
- 不要用 OpenRouter 替代已选择的 OpenAI/Codex，反之亦然。

### 7. L2 结论边界

测试计划列出的 L2 是候选观察范围，不是绿色继承列表。每个 journey 完成后，只把确有可观察证据的 L2 写入 `observed_l2`；每项包含：

- `category`
- `level_2_feature`
- `observation`
- `evidence_path`
- `supported`：`true`、`false` 或 `partial`

不要生成 atomic feature 或修改 atomic status。不要声称一个 journey PASS 就证明其关联 L2 的所有边界。

## 实现与运行顺序

1. 先实现 evidence recorder、sandbox、process cleanup、redaction 和 selector 结构。
2. 实现并运行 P22-J01。
3. 实现本地任务 P22-J03、J04、J07、J08、J10。
4. 实现 P22-J05、J06、J09；有环境就运行，没有就产生精确 gate 记录。
5. 最后实现 P22-J02；仅在明确 live-provider 授权和运行环境齐备时执行。
6. 运行所有已实现的非 live journeys；逐个修复测试本身的问题。
7. 运行 `git diff --check`，检查没有 credential、Excel lock、真实 home 路径或运行输出进入待提交测试代码。

## 完成质量门槛

- 十个 journey 各有一个可收集的测试 selector。
- 所有本地可运行任务都实际运行过，不能用 `NOT_TESTED` 代替失败。
- 每个已运行任务都有完整 evidence manifest 和可复现命令。
- live/network 未运行项有准确 gate，不伪造 PASS。
- 测试没有修改生产代码，没有触碰共享 matrix/workbook/progress log。
- teardown 后没有遗留进程、tmux session 或监听端口。
- 结果文件中十个 journey ID 恰好各出现一次。

## 最终回复格式

请报告：

1. 新增/修改了哪些测试和 helper。
2. 十个 journey 的 selector 列表。
3. 哪些实际运行，分别是 PASS、PASS_WITH_KNOWN_LIMITATIONS、FAIL、ENVIRONMENT_BLOCKED、NOT_AVAILABLE、NOT_TESTED 的数量。
4. 每个失败或阻塞的简短原因。
5. 非 live 与 live 测试的准确运行命令。
6. `.codex-tmp/phase22-worker-results/journey-code-batch-001/result.json` 的绝对路径。
7. 明确声明未修改 full/brief workbook、matrix 和 progress log。
