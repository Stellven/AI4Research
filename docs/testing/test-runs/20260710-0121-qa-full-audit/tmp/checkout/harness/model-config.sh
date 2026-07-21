#!/bin/bash
# Solar Harness — 模型路由配置
# 按需用 Zhipu GLM 或 Claude OAuth
# 注：tmux 内 Claude OAuth 实测可用 (2026-05-08 验证 planner+evaluator+builder pane 均跑 Claude Max)
# persona 模型选择见 lib/persona-config.sh, 默认: planner/evaluator/pm=Opus, builder=GLM-5.1→Sonnet fallback

export ZHIPU_BASE_URL="https://api.z.ai/api/anthropic"
export ZHIPU_MODEL="GLM-5.1"
export ZHIPU_TOKEN_SOURCE="${ZHIPU_TOKEN_SOURCE:-unset}"

# Token 从 secrets 文件读取，不硬编码。
# 优先级：
#   1. ~/.solar/secrets/zhipu.env             # 专用 Coding Plan token
#   2. ~/.solar/secrets/solar-user-secrets.env # UI/用户配置
#   3. 进程环境变量                            # 手动临时覆盖
SECRETS_FILE="$HOME/.solar/secrets/zhipu.env"
if [[ -f "$SECRETS_FILE" ]]; then
  source "$SECRETS_FILE"
  export ZHIPU_TOKEN_SOURCE="zhipu.env"
fi

USER_SECRETS_FILE="$HOME/.solar/secrets/solar-user-secrets.env"
if [[ -z "${ZHIPU_AUTH_TOKEN:-}" && -f "$USER_SECRETS_FILE" ]]; then
  source "$USER_SECRETS_FILE"
  export ZHIPU_TOKEN_SOURCE="solar-user-secrets.env"
fi

if [[ -n "${ZHIPU_AUTH_TOKEN:-}" && "${ZHIPU_TOKEN_SOURCE:-unset}" == "unset" ]]; then
  export ZHIPU_TOKEN_SOURCE="environment"
fi

# 兼容旧命名 ZHIPU_API_KEY
if [[ -n "${ZHIPU_AUTH_TOKEN:-}" ]]; then
  export ZHIPU_API_KEY="$ZHIPU_AUTH_TOKEN"
fi

# 缺失凭据时不要直接 exit。
# 启动链会在 persona-config.sh 内决定是否回退到 Claude 默认模型。

# SOLAR_NO_ZHIPU 持久化 flag (2026-05-07): tmux respawn-pane 时一次性 env 会丢失,
# 改用 flag 文件,每次 source model-config.sh 自动恢复.
# 删除 flag 即可恢复 GLM 优先: rm ~/.solar/secrets/no-zhipu.flag
if [[ -f "$HOME/.solar/secrets/no-zhipu.flag" ]]; then
  export SOLAR_NO_ZHIPU=1
fi
