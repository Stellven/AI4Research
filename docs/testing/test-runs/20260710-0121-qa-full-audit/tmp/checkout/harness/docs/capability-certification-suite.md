# Solar Capability Certification Suite

目标：用本地、可复验的证据判断 Solar/Solar-Harness 的能力是否“完整、完全、自动、默认、可用、有效”。

## 一条命令

```bash
solar-harness integrations certify --mode fast
solar-harness integrations certify --mode full
solar-harness integrations certify --mode heavy
```

产物：

- `~/.solar/harness/reports/capability-certification-latest.json`
- `~/.solar/harness/reports/capability-certification-latest.md`
- `~/.solar/harness/reports/capability-certification-evidence/latest/`

## 认证维度

```text
┌───────────┬────────────────────────────────────────────────────────────┐
│ 维度      │ 判定口径                                                   │
├───────────┼────────────────────────────────────────────────────────────┤
│ complete  │ 能力清单、插件、skill、capability registry 有覆盖           │
│ default   │ 默认 coordinator / DAG dispatch 路径会注入能力上下文        │
│ automatic │ 任务文本自动命中 intent/capability，无需人工挑 skill        │
│ usable    │ CLI、脚本、runtime、pane 配置可实际运行                     │
│ effective │ 正例命中、负例不乱命中，benchmark 有分数和证据              │
│ evidence  │ 每个判断都有 JSON/Markdown/命令输出证据                    │
└───────────┴────────────────────────────────────────────────────────────┘
```

## 模式

```text
┌───────┬────────────────────────────────────────────────────────────────┐
│ 模式  │ 覆盖                                                           │
├───────┼────────────────────────────────────────────────────────────────┤
│ fast  │ 语法、intent、skills inject、DAG dispatch、capability E2E、Ruflo │
│ full  │ fast + capability fusion benchmark + platform workflow + arena  │
│ heavy │ full + 浏览器/模型/重型 runtime proof                           │
└───────┴────────────────────────────────────────────────────────────────┘
```

## PASS 规则

- `ok`：本地命令通过，并写入证据文件。
- `warn`：外部 runtime 或登录态导致的允许失败，不隐藏，但不阻塞主认证。
- `error`：阻塞失败；不能声明该能力“完整/默认/有效”。

## 负例控制

套件会构造一个无关任务 `Compute 2 + 2 only.`，要求：

- 仍插入基础 context block。
- 不得误命中 `gstack`、`Browser-use MCP`、`Ruflo`、`MarkItDown`、`Empirical Research`。
- 查询不存在 capability 必须失败，防止 benchmark 无条件 PASS。
