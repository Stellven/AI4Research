#!/bin/bash
# Solar PermissionRequest Hook
# 自动批准安全操作，拒绝危险操作，其余交给用户
# 触发: PermissionRequest
# 性能目标: <5ms (纯 bash + grep，无 jq)

# ── 提取 stdin ──

INPUT=$(cat)

# 容错提取 tool_name (支持多种字段名格式)
TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' 2>/dev/null)
[ -z "$TOOL_NAME" ] && TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' 2>/dev/null)
[ -z "$TOOL_NAME" ] && exit 0

# 提取 command (仅 Bash 工具需要)
COMMAND=$(echo "$INPUT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' 2>/dev/null)

# ── 1. 读取类工具 → 直接批准 ──

case "$TOOL_NAME" in
    Read|Glob|Grep)
        echo "approve"
        exit 0
        ;;
esac

# ── 2. Bash 命令分析 ──

if [[ "$TOOL_NAME" == "Bash" ]]; then
    # 提取管道前的第一个命令
    FIRST_CMD=$(echo "$COMMAND" | sed 's/|.*//' | awk '{print $1}')
    # 去掉路径前缀 (如 /usr/bin/ls → ls)
    FIRST_CMD=$(basename "$FIRST_CMD" 2>/dev/null)

    # 2a. 安全只读命令
    case "$FIRST_CMD" in
        ls|cat|head|tail|wc|echo|which|type|pwd|whoami|date|uptime|uname|file|stat|du|df|env|printenv|md5|shasum|md5sum|sha256sum|base64|tr|sort|uniq|cut|tee|realpath|readlink|dirname|basename)
            echo "approve"
            exit 0
            ;;
    esac

    # 2b. git 只读操作
    if echo "$COMMAND" | grep -qE '^git\s+(status|log|diff|branch|remote|show|stash(\s+list)?|tag|rev-parse|describe|shortlog|blame)'; then
        echo "approve"
        exit 0
    fi

    # 2c. 目录操作 (非系统目录)
    case "$FIRST_CMD" in
        cd|mkdir)
            # 拒绝写入系统目录
            if echo "$COMMAND" | grep -qE '(^|[[:space:]])(/etc|/usr|/System|/Library|/sbin|/bin)([[:space:]]|$|/)'; then
                echo "deny"
                exit 0
            fi
            echo "approve"
            exit 0
            ;;
    esac

    # 2d. 查询类工具
    case "$FIRST_CMD" in
        python3|node|bun|deno|npm|pip3|cargo|go)
            # 仅批准查询/列表类参数
            if echo "$COMMAND" | grep -qE '(--[Vv]ersion|--help|list|show|info|search|why|la|ll)\b'; then
                echo "approve"
                exit 0
            fi
            # 其余交给用户
            exit 0
            ;;
    esac

    # 2e. 危险操作检测 (deny 优先于 approve)
    # rm -rf / 或 rm -rf /*
    if echo "$COMMAND" | grep -qE 'rm\s+(-[a-zA-Z]*f[a-zA-Z]*[[:space:]]+)+(/+|/\*)'; then
        echo "deny"
        exit 0
    fi

    # sudo
    if echo "$COMMAND" | grep -qE '(^|[[:space:];|&])sudo([[:space:]]|$)'; then
        echo "deny"
        exit 0
    fi

    # git push --force 到 main/master
    if echo "$COMMAND" | grep -qE 'git\s+push.*--force.*(main|master)'; then
        echo "deny"
        exit 0
    fi

    # chmod 777 / chown
    if echo "$COMMAND" | grep -qE 'chmod[[:space:]]+777\b' || echo "$COMMAND" | grep -qE '(^|[[:space:];|&])chown([[:space:]]|$)'; then
        echo "deny"
        exit 0
    fi

    # 写入系统目录 (/etc, /usr, /System, /Library)
    if echo "$COMMAND" | grep -qE '(>|>>)[[:space:]]*(/etc/|/usr/|/System/|/Library/)'; then
        echo "deny"
        exit 0
    fi

    # mktemp, touch 等无害文件操作
    case "$FIRST_CMD" in
        mktemp|touch|tree|nc|curl|ssh-keygen|git\?)
            echo "approve"
            exit 0
            ;;
    esac
fi

# ── 3. 其余交给用户手动决定 ──

exit 0
