## 模式触发

> **统一意图引擎处理**: 所有意图检测由 `intent-engine-hook.sh` 统一处理，详见 `rules/intent-engine.md`

| 触发词 | 动作 |
|--------|------|
| solar/打开solar | → 加载 Solar 上下文 + 启动宣告 |
| 批准/approved | → 执行宣告中的请求 |
| 我要开发 | → 开发模式 |
| 我要办公 | → 办公模式 |

## 懒加载规则
1. 启动: 只读 kernel (SOLAR.md)
2. 触发词: 按上方模式触发表执行
3. /命令: 读对应 skills/*/SKILL.md
4. @Agent: 读对应 agents/*.md
