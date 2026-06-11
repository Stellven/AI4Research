# Solar 铁律: Cortex First

> 设计/开发前必须先查 Cortex，基于证据决策

## 统一查询入口

```bash
# 日常查询：使用已安装的 Solar runtime DB，不依赖仓库外脚本
python3 - "$HOME/.solar/db/solar.db" "关键词" <<'PY'
import os
import sqlite3
import sys

db_path, query = sys.argv[1], sys.argv[2]
if not os.path.exists(db_path):
    raise SystemExit(f"Cortex DB not found: {db_path}")

con = sqlite3.connect(db_path)
try:
    rows = con.execute(
        """
        SELECT title, substr(finding, 1, 160), credibility
        FROM cortex_sources
        WHERE title LIKE ? OR finding LIKE ?
        ORDER BY credibility DESC
        LIMIT 10
        """,
        (f"%{query}%", f"%{query}%"),
    ).fetchall()
finally:
    con.close()

for title, finding, credibility in rows:
    print(f"[{credibility}] {title}: {finding}")
PY
```

## 决策流程

```
需求到达 → 查询 Cortex DB → 有证据? → 基于证据设计
                              ↓ 无
                         补充研究 → 记录来源 → 设计
```

## 证据质量要求

- credibility / confidence ≥ 0.7 才可信
- 无证据时必须调用 /insight 研究
- 决策必须标注证据来源 (citation_key)
