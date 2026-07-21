#!/usr/bin/env python3
"""
D3: 从 Cortex 迁移 50 条高质量数据到 MemPalace

选择策略: 按 credibility DESC LIMIT 50
"""

import sqlite3
import sys
from pathlib import Path

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent))

from mempalace_init import MemPalaceInit

# 初始化 MemPalace
_init = None
def get_init():
    global _init
    if _init is None:
        _init = MemPalaceInit()
        _init.init_chromadb()
        _init.load_models()
    return _init

def mempalace_add(text: str, source: str = "cortex", entity_codes: list = None):
    """直接添加文档（不通过 MCP）"""
    init = get_init()
    from datetime import datetime

    lang = init.detect_language(text)
    doc_id = init.generate_id(text, source)
    model = init.get_model(lang)
    embedding = model.encode(text).tolist()

    metadata = {
        "source": source,
        "lang": lang,
        "created_at": datetime.utcnow().isoformat(),
        "entity_codes": ",".join(entity_codes or [])
    }

    init.collection.add(
        ids=[doc_id],
        embeddings=[embedding],
        metadatas=[metadata],
        documents=[text]
    )

    return {
        "doc_id": doc_id,
        "success": True,
        "lang": lang
    }

# Cortex DB 路径
CORTEX_DB = Path.home() / ".solar" / "solar.db"


def migrate_top_cortex(limit: int = 50):
    """迁移 Cortex 高 cred 数据到 MemPalace"""
    conn = sqlite3.connect(CORTEX_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 查询高 cred 数据
    sql = '''
    SELECT citation_key, title, finding, credibility, task_id
    FROM cortex_sources
    WHERE credibility IS NOT NULL
    ORDER BY credibility DESC
    LIMIT ?
    '''

    cursor.execute(sql, (limit,))
    rows = cursor.fetchall()

    print(f"Found {len(rows)} Cortex entries to migrate...")

    success_count = 0
    fail_count = 0

    for row in rows:
        # 准备文档
        text = f"{row['title']}\n\n{row['finding']}"
        source = "cortex"

        # 提取实体码（从 citation_key 或 task_id）
        entity_codes = ["COR"]  # 默认
        if row['task_id']:
            # 从 task_id 提取简码
            task_code = row['task_id'].split('-')[0][:3].upper()
            entity_codes.append(task_code)

        try:
            result = mempalace_add(
                text=text,
                source=source,
                entity_codes=entity_codes
            )

            if result.get("success"):
                success_count += 1
                print(f"✓ Migrated: {row['citation_key']} (cred={row['credibility']})")
            else:
                fail_count += 1
                print(f"✗ Failed: {row['citation_key']} - {result.get('error', 'Unknown error')}")
        except Exception as e:
            fail_count += 1
            print(f"✗ Error: {row['citation_key']} - {e}")

    conn.close()

    print(f"\n=== Migration Summary ===")
    print(f"Total: {len(rows)}")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")

    return success_count, fail_count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate Cortex data to MemPalace")
    parser.add_argument("--limit", type=int, default=50, help="Number of entries to migrate")
    args = parser.parse_args()

    migrate_top_cortex(args.limit)
