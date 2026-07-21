#!/bin/bash
# texture-inject.sh - 三层纹理穿插机制 v1.0
# 用途：根据层级和场景从 behavior_textures 表注入行为样本
#
# 参数：
#   $1 - 层级: head/mid/tail
#   $2 - 场景关键词 (可选)

set -euo pipefail

DB="${HOME}/.solar/solar.db"
LAYER="${1:-head}"
SCENE="${2:-}"

# 根据层级选择纹理
case "$LAYER" in
  head)
    # 首层：人格 + 核心法则
    TEXTURES=$(sqlite3 "$DB" "
      SELECT behavior_sample FROM behavior_textures
      WHERE (layer = 'head' OR layer = 'all')
      AND (category = 'persona' OR category = 'law')
      ORDER BY RANDOM()
      LIMIT 4;
    " 2>/dev/null | tr '\n' ' ')
    ;;

  mid)
    # 中层：场景匹配 + 人格微提醒
    if [ -n "$SCENE" ]; then
      TEXTURES=$(sqlite3 "$DB" "
        SELECT behavior_sample FROM behavior_textures
        WHERE (layer = 'mid' OR layer = 'all')
        AND (trigger_keywords LIKE '%$SCENE%' OR category = 'persona')
        ORDER BY success_count DESC
        LIMIT 2;
      " 2>/dev/null | tr '\n' ' ')
    else
      TEXTURES=$(sqlite3 "$DB" "
        SELECT behavior_sample FROM behavior_textures
        WHERE layer = 'mid' AND category = 'persona'
        LIMIT 1;
      " 2>/dev/null)
    fi
    ;;

  tail)
    # 尾层：执行提醒 + 人格签名
    TEXTURES=$(sqlite3 "$DB" "
      SELECT behavior_sample FROM behavior_textures
      WHERE (layer = 'tail' OR layer = 'all')
      ORDER BY RANDOM()
      LIMIT 2;
    " 2>/dev/null | tr '\n' ' ')
    ;;
esac

# 如果有纹理，输出为上下文提示
if [ -n "$TEXTURES" ]; then
  echo "<BEHAVIOR_TEXTURE layer=\"$LAYER\">"
  echo "以下是我(Solar)的行为样本，请用类似的语气和方式回应："
  echo "$TEXTURES"
  echo "</BEHAVIOR_TEXTURE>"
fi
