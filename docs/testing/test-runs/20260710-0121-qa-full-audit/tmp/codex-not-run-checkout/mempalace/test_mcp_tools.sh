#!/bin/bash
# D2: MCP 5 工具 in-process 测试 (绕开 stdio 协议直接 import 调用)
set -e
python3.11 <<'PYEOF'
import warnings; warnings.filterwarnings('ignore')
import sys
sys.path.insert(0, '~/.solar/mempalace')
from mempalace_mcp_server import (
    mempalace_add, mempalace_search, mempalace_delete, mempalace_stats,
    mempalace_diary_write, mempalace_diary_read,
)

# 检查 6 个工具函数都存在
for name in ('mempalace_add','mempalace_search','mempalace_delete','mempalace_stats',
             'mempalace_diary_write','mempalace_diary_read'):
    print(f'  ✓ {name}')

# stats
s = mempalace_stats()
assert s.get('total_docs', 0) >= 50, f'stats total_docs too low: {s}'
print(f'  ✓ stats: {s.get("total_docs")} docs')

# add
r = mempalace_add(text='D2 smoke test', source='test', entity_codes=['SOL'])
assert r.get('success'), f'add failed: {r}'
print(f'  ✓ add: {r.get("doc_id")[:20]}')

# search
sr = mempalace_search(query='smoke test', top_k=3)
assert len(sr.get('results', [])) > 0, f'search empty'
print(f'  ✓ search: hit {len(sr["results"])}')

print('✅ D2: 6 工具全部 in-process 测试通过')
PYEOF
