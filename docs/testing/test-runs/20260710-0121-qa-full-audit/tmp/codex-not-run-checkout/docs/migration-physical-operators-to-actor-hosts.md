# Migration — physical-operators → actor-hosts

## Overview

本页落地物理算子到 actor-hosts 的兼容迁移策略，确保 S03 执行期 `physical-operators.json` 只承担兼容职责，不再承担新实例创建的 source-of-truth 角色。

- 主链路：
  - 写入与运行期路由优先使用 `config/actor-hosts.json`。
  - `config/physical-operators.json` 仅保留兼容字段：`compat_alias_for` + `compat_maps_to`。
- 迁移边界：
  - 不新增硬编码 token/path；仅在映射规则层描述语义。
  - 所有旧 `legacy` 条目须可通过兼容表映射到现有 8 类 `host_type`。

## Mapping Table

| legacy_source | compat_alias_for | compat_maps_to.host_type | carrier_meta 字段 |
|---|---|---|---|
| `pane_*`（`pane_builder`、`pane_evaluator`、`pane_architect`） | `tmux_pane` | `tmux_pane` | `tmux_pane_meta` |
| `codex_worktree_*`（`mini-codex-builder`、`browser_profile_host`） | `codex_worktree` | `codex_worktree` | `codex_worktree_meta` |
| `antigravity_*`（`mini-antigravity-host`） | `antigravity_managed_env` | `antigravity_managed_env` | `antigravity_managed_env_meta` |
| `mlx_*`（`mini-thunderomlx`） | `local_mlx_process` | `local_mlx_process` | `local_mlx_process_meta` |
| `ssh_devbox_*`（`ssh_devbox` / `ssh_devbox_remote`） | `ssh_devbox` | `ssh_devbox` | `ssh_devbox_meta` |
| `legacy_cloud_*`（回退兼容） | `local_docker_compat_alias` | `local_docker`（或等效兼容 host_type） | `legacy_cloud_meta` |

说明：表头中的五类 carrier 必须都出现（`tmux_pane` / `codex_worktree` / `antigravity_managed_env` / `local_mlx_process` / `ssh_devbox`），其余行用于兼容过渡。

### 映射规则约束

- `compat_alias_for` 与 `compat_maps_to.host_type` 必须语义一致。
- `compat_maps_to` 必须包含 `carrier_hint`，其中 `carrier_hint` 至少包含：
  - `carrier_meta`（与目标 host_type 对应的元数据对象）
  - `carrier_hint_tier`
  - `migration_owner`

## Field Spec

### Operator-level（兼容项）

```json
{
  "id": "pane_builder",
  "compat_alias_for": "tmux_pane",
  "compat_maps_to": {
    "host_type": "tmux_pane",
    "carrier_hint": {
      "carrier_meta": {
        "tmux_pane_meta": {
          "session": "solar-harness",
          "window": 0,
          "pane": 1,
          "worktree": "main"
        }
      },
      "carrier_hint_tier": "compat",
      "migration_owner": "actor-hosts-transition"
    }
  },
  "deprecated": true,
  "compat_migration": {
    "status": "readonly",
    "sunset_plan": "S05"
  }
}
```

### File-level（根元信息）

```json
{
  "_meta": {
    "transition_status": "read_only",
    "transition_started_at": "2026-06-01T00:00:00Z",
    "deprecated_at": "2026-06-16T00:00:00Z",
    "sunset_target": "S05"
  }
}
```

- `transition_status` 必须与里程碑一致推进：`read_only` → `deprecated` → `sunset`。
- `compat_*` 字段只允许在兼容期内出现在 legacy 条目中。

## Timeline

| Sprint | transition_status | 目标动作 | 是否允许主链路写入 |
|---|---|---|---|
| S02 | read_only | 建立 compat 映射与校验逻辑，避免新增主链路写逻辑 | 否 |
| S03 | deprecated | 新增/变更优先落到 `actor-hosts.json`，保留 compat shim | 否 |
| S04 | deprecated | 完成 router/status 兼容读取与告警可观测 | 否 |
| S05 | sunset | 物理算子主链路仅保留降级兼容与 fail-fast 提示 | 否 |

S02 → S03 → S04 → S05 的 `transition_status` 流转：`read_only` → `deprecated` → `sunset`。

## Verification Commands

```bash
jq '.definitions.actor_host.properties.host_type.enum' config/actor-hosts.schema.json
```

```bash
jq '{
  total: (.operators|length),
  with_compat_alias: ([.operators[] | select(has("compat_alias_for"))] | length),
  with_compat_maps_to: ([.operators[] | select(has("compat_maps_to"))] | length),
  transition: ._meta.transition_status
}' config/physical-operators.json
```

```bash
jq '([
  .operators[] | select(type=="object") | .compat_maps_to.host_type
] | map(select(. != null)) | sort | unique)' config/physical-operators.json
```

```python3
import json
with open("config/physical-operators.json", "r", encoding="utf-8") as f:
    data = json.load(f)
required = {"tmux_pane", "codex_worktree", "antigravity_managed_env", "local_mlx_process", "ssh_devbox"}
for item in data.get("operators", []):
    if not isinstance(item, dict):
        continue
    host_type = item.get("compat_maps_to", {}).get("host_type")
    required.discard(host_type)
print("missing:", sorted(required))
print("transition_status:", data.get("_meta", {}).get("transition_status"))
```

```bash
python3 - <<'PY'
import json
with open("config/physical-operators.json", "r", encoding="utf-8") as f:
    data = json.load(f)
status = data.get("_meta", {}).get("transition_status")
if status not in {"read_only", "deprecated", "sunset"}:
    raise SystemExit(f"unexpected transition_status: {status}")
print("transition_status_ok")
PY
```

## Rollback Strategy

1. 文档/配置回退
   - 如出现兼容问题，立刻将 `_meta.transition_status` 回退为 `deprecated` 并冻结 S05 限制动作。
   - 回退后优先补齐不满足的 `compat_alias_for` 与 `carrier_meta` 缺失条目。
2. 兼容映射回放
   - 采用 `"compat_alias_for" + "compat_maps_to.host_type"` 回放回退路径，不修改历史条目 ID。
   - 若发现异常条目，先在 `physical-operators.json` 增补兼容别名，而非删除历史配置。
3. 运行期故障降级
   - 禁止直接新增 `physical-operators.json` 运行期主路由。
   - 如观测到误路由，回切 actor-hosts 主路由并在 24 小时内补齐回滚验证命令。
