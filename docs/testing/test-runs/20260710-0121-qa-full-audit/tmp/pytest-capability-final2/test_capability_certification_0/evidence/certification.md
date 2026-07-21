# Solar Capability Certification — 2026-07-13T16:26:52Z

- Mode: `fast`
- Result: `FAIL`
- Evidence: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/pytest-capability-final2/test_capability_certification_0/evidence`
- Blocking: `graph-dispatcher, model-call-runtime, capability-plane-e2e, expanded-capability-plane, ruflo-integration`
- Warnings: `N/A`

## Dimension Verdict

| Dimension | Status | OK/Total | Meaning |
|---|---:|---:|---|
| complete | error | 0/3 | 能力清单、插件、skill、capability registry 有覆盖。 |
| default | error | 1/4 | 默认 dispatch/coordinator/DAG 路径会注入能力上下文。 |
| automatic | error | 2/3 | 无需人工挑 skill，任务文本自动命中 intent/capability。 |
| usable | error | 2/6 | CLI、脚本、runtime、pane 配置能实际运行。 |
| effective | ok | 3/3 | 正例命中、负例不乱命中，benchmark 有分数和证据。 |
| evidence | error | 1/2 | 每个判断都有 JSON/Markdown/命令输出证据。 |

## Checks

| Check | Status | Dimensions | Exit | Duration |
|---|---:|---|---:|---:|
| syntax-core | ok | usable | 0 | 0.054s |
| bash-syntax | ok | usable | 0 | 0.012s |
| intent-adapter | ok | automatic,effective | 0 | 0.785s |
| skills-inject | ok | default,automatic,effective | 0 | 0.741s |
| graph-dispatcher | error | default,automatic | 1 | 0.689s |
| model-call-runtime | error | default,usable,evidence | 2 | 0.035s |
| capability-plane-e2e | error | complete,usable | 1 | 4.567s |
| expanded-capability-plane | error | complete,usable | 1 | 4.232s |
| ruflo-integration | error | complete,default,usable | 1 | 0.306s |
| negative-controls | ok | effective,evidence | 0 | 0s |

## Standard

- `ok`: check passed with local evidence.
- `warn`: non-blocking known external/runtime dependency failed and is explicitly marked allow-fail.
- `error`: blocking failure; capability cannot be claimed as complete/default/effective.
