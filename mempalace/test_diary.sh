#!/bin/bash
# D4: AAAK 日记函数测试
set -e
python3.11 <<'PYEOF'
import warnings; warnings.filterwarnings('ignore')
import sys
sys.path.insert(0, '~/.solar/mempalace')
from mempalace_mcp_server import mempalace_diary_write, mempalace_diary_read

# 1. 写一条日记
r = mempalace_diary_write(agent_name='SOL', entry='diary smoke test', topic='test')
assert r.get('success'), f'write failed: {r}'

# 2. 读 SOL agent 应能拿到
recs = mempalace_diary_read(agent_name='SOL', topic='test', limit=5)
assert any('smoke test' in str(r) for r in recs), 'SOL agent 读不回写入'

# 3. 读 HGR agent 不应拿到 SOL 的
hgr_recs = mempalace_diary_read(agent_name='HGR', topic='test', limit=5)
assert not any('smoke test' in str(r) for r in hgr_recs if r.get('agent') != 'HGR'), 'agent 过滤失败'

print('✅ AAAK 日记 3 项验证通过')
PYEOF
