# 多阶段模型输出合同适配 — 2026-08-31

本次用户授权修复所有阶段的模型输出请求，并按模型 registry 兼顾各 provider。
这不是新机部署或线上 E2E 验收。未启动 backend、Scheduler、旧 session 或线上模型任务。

## 修复边界

原始合同仍是验收权威；没有修改 compiler/planning/evidence 下的业务 Schema。
`harness/lib/structured_output.py` 生成服务可接受的副本，并校验返回数据。
`harness/lib/structured_model.py` 统一模型选择、传输、响应解析和调用回执。

- Intent 生成与独立 fidelity review。
- Requirement 的动态 compiler/reviewer schema（包含实际 registry/Intent ID 枚举）。
- Planner 的决策、PlanIR、fidelity、能力选择、组合选择、能力适配审查。
- Planner/下游 direct-answer 的生成和评审。
- 固定科研流程的 evidence synthesis、report draft/revision、independent/revision review。
- 独立 artifact review 的 OpenAI 原生 `response_format` 使用同一投影器。

已有 OpenAI-compatible 科研 API、知识处理等仅请求 `json_object` 或普通文本的路径，
不会把业务 Schema 当原生服务 Schema 提交，故不受本次 `required` 拒绝影响。
它们的既有领域验证和路由保留；不宣称本次已迁移整个仓库的所有非结构化模型调用。

## 原故障与语义保持

最后一次 E2E 的 `cpu_cores_min`、`memory_mb_min`、`gpu_required` 原本是可选字段。
OpenAI 的提交副本将所有对象属性列入 required，可选且不允许 null 的字段加入 nullable 表达。
返回时只将这类字段的 null 恢复为缺省；明确的 0、false、数值及原本允许的 null 都保留。
不得填充 CPU、内存或 GPU 默认要求，也不得修改冻结 SchedulerInput 的业务含义。

枚举/常量补充显式类型，const 转为单值 enum；元 Schema、tuple 和其他不通用约束仅在
提交副本中处理。原始范围、位置、唯一性、oneOf、必填项及额外字段限制在返回时校验。
不支持的结构在调用前失败，不通过关闭本地校验或自动换 provider 来继续。

每次通用调用记录 source/wire schema 哈希、模型、provider、transport、schema_mode、
耗时及成功/失败状态。JSON 重复键、非有限数字、非 JSON 文本、不合约输出、拒答、截断、
tool-call 终止不能变成成功。HTTP 错误不复制响应正文或认证信息；不跟随 endpoint 重定向。

## Registry 与服务差异

`harness/config/model-registry.json` 的 11 个模型条目和别名保持不变，新增
`structured_output_providers`。GLM/DeepSeek 使用 `structured_model` 指定真实 API 模型名，
不能把旧 Claude proxy 的 `--model opus/sonnet` 当作它们的 API 模型 ID。

| Provider / registry 模型 | 默认传输与格式 | 边界 |
| --- | --- | --- |
| OpenAI：GPT 5.5、Codex Spark、ChatGPT 5.5 | Codex CLI 原生 Schema；可显式选 chat_completions API | registry 名称不证明对应账号/接口实际提供该模型，尤其 ChatGPT 别名必须实测 |
| Anthropic：Claude Opus、Claude Sonnet | Claude CLI prompt JSON；可显式选 Anthropic Messages API | 通用编译链含递归合同，采用保守策略；非递归合同可显式选 native。解析 structured_output/result 并完整校验 |
| Zhipu：GLM 5.1、GLM 4.7 | chat_completions JSON object | 不发送 OpenAI strict schema；本地按原合同验收 |
| DeepSeek V4 Pro | chat_completions JSON object | 同上，不自动走 Claude proxy 或换服务 |
| Gemini 2.5 Pro / Flash | generateContent JSON MIME | Intent 含必填递归引用；默认不发送不兼容的原生 Schema。native 可显式选择，但遇递归会预检拒绝 |
| ThunderOMLX | 显式配置的本地 chat_completions endpoint，prompt JSON | 不假设本地服务器支持原生 Schema 或 JSON mode；必须配置实际模型和地址 |

Gemini 的 schema 支持和 OpenAI 不同：必填递归引用不能仅靠 nullable 修好；bool/null enum
也不能照搬。默认 JSON MIME + 原合同本地校验是明确的 registry 策略，不是失败后的静默降级。
JSON 模式保证能力弱于原生约束生成，因此不合约输出仍可能失败；这不削弱验收条件。

Claude 通用编译链同样不假设服务支持递归 Schema；原生适配器只接受非递归结构。
这是尚未实测递归能力时的保守适配策略，不是新的线上失败结论。固定科研流程的五份
非递归合同仍使用 Claude 原生 Schema。通用 Anthropic API 的 Sonnet 条目明确映射到
`claude-sonnet-4-6`，CLI 保留 `sonnet`；不能把 CLI 简写直接作为 API ID。
历史 registry 的裸 `sonnet` 别名属于 GLM 4.7；选 Claude 请用 `claude-sonnet`。

## 配置

生成和评审均独立支持 `SOLAR_<STAGE>_<ROLE>_MODEL/PROVIDER`，其中 STAGE 为
`INTENT`、`REQUIREMENT`、`PLANNER`、`DIRECT_ANSWER`，ROLE 为 `COMPILER`、`REVIEWER`。
其次使用 stage 的 MODEL/PROVIDER，再使用 `SOLAR_LLM_MODEL/PROVIDER`。未选择模型时保留
原 Codex 默认路径；direct-answer 保留其 GPT 5.5 默认值。显式 provider 与 registry 模型
冲突会报错；不认识的模型 ID 必须显式指定 provider，不会猜一个服务。

provider 层可用 `SOLAR_LLM_<PROVIDER>_TRANSPORT/SCHEMA_MODE/ENDPOINT/KEY_ENV/MODEL/MAX_OUTPUT_TOKENS`
覆盖配置。ENDPOINT 是完整 API endpoint；Gemini 是 `/v1beta` 根地址。
本地服务必须指定 `SOLAR_LLM_LOCAL_ENDPOINT` 和 `SOLAR_LLM_LOCAL_MODEL`。
KEY_ENV 是环境变量名，不是 key 本身；不读取或复制个人凭据文件来配置新 API。
Claude CLI 若带有非 Anthropic 的 ANTHROPIC_BASE_URL proxy，会要求显式选择对应 provider。

固定科研流程保留 `SOLAR_RESEARCH_MODEL_PROVIDER`、`SOLAR_RESEARCH_MODEL`，并增加通用
`SOLAR_RESEARCH_REVIEWER_MODEL`（兼容旧 SOLAR_CODEX_REVIEW_MODEL）。新增 Gemini、GLM、
DeepSeek、本地服务接入同一模型层；实际 provider、角色、所有 transport evidence 文件
进入原有共享 invocation journal，来源门禁继续拒绝 provider 不匹配。
历史 OpenAI/OpenRouter API 科研路径保留其显式 AUTOSCI 配置要求，没有自动开启。

API 默认读取 OPENAI_API_KEY、ANTHROPIC_API_KEY、ZHIPU_API_KEY、DEEPSEEK_API_KEY、
GEMINI_API_KEY/GOOGLE_AI_API_KEY 或 THUNDEROMLX_AUTH_TOKEN。
Z.AI 与 BigModel 的 endpoint/凭据不可混用；使用 Z.AI 时显式配置其 endpoint 和 KEY_ENV。
CLI 登录、API key、模型授权是不同条件。另一个 scenario-routing registry 的启用项
不意味着新结构化调用已取得该账号权限，本次没有修改它或安装/登录任何模型 CLI。

## 验证方式与限制

`harness/tests/test_structured_model_contracts.py` 在真实调用层拦截进程/HTTP 边界，覆盖
11 个 registry 模型 × 15 份 compiler/planner Schema、有效结果往返、资源字段恢复、
阶段 factory、动态 Requirement 合同修复、科研服务与来源证据、拒答/截断/缺少认证。
假响应不属于线上模型证据。最终命令、计数、耗时以问题日志的新条目和本地 JUnit 为准。
最终复验为 284 passed、0 failed、0 skipped（134.47 s）；本地证据清单为
`.codex-tmp/structured-output-verification.json`，保存 19 个变动源码/配置文件的哈希。
Planner 的服务失败和本地合约失败都会生成拒绝记录，不产生 Scheduler 交接权限。
没有增加自动重试或切换模型；不合约响应可能终止当前步骤，语义修复和 Requirement
结构修复仍遵守各自原有次数与截止时间。

在新环境完成真实的各模型 Schema 接受测试及 E2E 前，线上状态仍为 NOT_TESTED。
不保证 registry 中每个历史模型 ID 目前在每个服务或账号可用；不承诺修复接口格式后
模型生成的语义一定正确。旧的 2026-08-31 E2E FAIL 记录不回写为 PASS。

## 规则来源

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Claude Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Claude Model IDs and versions](https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions)
- [Gemini generateContent / GenerationConfig](https://ai.google.dev/api/generate-content#v1beta.GenerationConfig)
- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)
- [Z.AI Structured Output](https://docs.z.ai/guides/capabilities/struct-output)
