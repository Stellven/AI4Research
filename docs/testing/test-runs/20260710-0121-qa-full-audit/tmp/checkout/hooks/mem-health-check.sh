#!/bin/bash
# Solar 记忆系统健康诊断
# 用法: bash ~/.claude/hooks/mem-health-check.sh
# 或 cron: 每日 8:00 检查一次

MEMPAL_DIR="$HOME/.mempalace"
SOLAR_DIR="$HOME/.solar"
PYTHON="$MEMPAL_DIR/venv/bin/python3"

echo "========================================"
echo "  Solar 记忆系统健康诊断"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo ""

# ── 1. MemPalace Drawers ───────────────────
echo "【MemPalace Drawers】"
if [[ -d "$MEMPAL_DIR/palace" ]]; then
    "$PYTHON" -c "
import chromadb
client = chromadb.PersistentClient(path='$MEMPAL_DIR/palace')
col = client.get_collection('mempalace_drawers')
total = col.count()
# 按 wing 统计
wings = {}
batch = col.get(limit=min(total, 5000), include=['metadatas'])
for m in batch['metadatas']:
    w = m.get('wing', 'unknown')
    wings[w] = wings.get(w, 0) + 1
print(f'  总数: {total}')
for w, c in sorted(wings.items(), key=lambda x: -x[1])[:5]:
    print(f'  {w}: {c}')
" 2>/dev/null
else
    echo "  ⚠ MemPalace 目录不存在"
fi
echo ""

# ── 2. 知识图谱 ────────────────────────────
echo "【知识图谱 (KG)】"
if [[ -f "$MEMPAL_DIR/knowledge_graph.sqlite3" ]]; then
    "$PYTHON" -c "
import sqlite3
db = sqlite3.connect('$MEMPAL_DIR/knowledge_graph.sqlite3')
ents = db.execute('SELECT COUNT(*) FROM entities').fetchone()[0]
tris = db.execute('SELECT COUNT(*) FROM triples').fetchone()[0]
orphans = db.execute('SELECT COUNT(*) FROM entities WHERE name NOT IN (SELECT subject FROM triples UNION SELECT object FROM triples)').fetchone()[0]
print(f'  实体: {ents}')
print(f'  关系: {tris}')
print(f'  孤立实体: {orphans} ({100*orphans//max(ents,1)}%)')
# 最近活跃
recent = db.execute('SELECT subject, predicate, object FROM triples ORDER BY rowid DESC LIMIT 3').fetchall()
print(f'  最近关系:')
for s, p, o in recent:
    print(f'    {s} → {p} → {o[:50]}')
db.close()
" 2>/dev/null
else
    echo "  ⚠ KG 数据库不存在"
fi
echo ""

# ── 3. Diary ───────────────────────────────
echo "【AAAK 日记】"
"$PYTHON" -c "
import sqlite3
db = sqlite3.connect('$MEMPAL_DIR/knowledge_graph.sqlite3')
try:
    count = db.execute('SELECT COUNT(*) FROM diary_entries').fetchone()[0]
    print(f'  总条目: {count}')
    recent = db.execute('SELECT entry, timestamp FROM diary_entries ORDER BY id DESC LIMIT 3').fetchall()
    for entry, ts in recent:
        print(f'  [{ts}] {entry[:80]}')
except:
    print('  (diary 表不存在)')
db.close()
" 2>/dev/null
echo ""

# ── 4. Recall 命中率 ──────────────────────
echo "【召回命中率 (最近 20 次)】"
if [[ -f "$SOLAR_DIR/session-state.jsonl" ]]; then
    "$PYTHON" -c "
import json
hits = {'p0': 0, 'p1': 0, 'p2': 0, 'total': 0}
for line in open('$SOLAR_DIR/session-state.jsonl'):
    line = line.strip()
    if not line: continue
    try:
        d = json.loads(line)
        if d.get('event') == 'recall_analytics':
            hits['total'] += 1
            if d.get('p0_mempl'): hits['p0'] += 1
            if d.get('p1_mem0'): hits['p1'] += 1
            if d.get('p2_fts5'): hits['p2'] += 1
    except: pass
if hits['total'] > 0:
    print(f'  总召回次数: {hits[\"total\"]}')
    print(f'  Phase 0 (MemPalace): {hits[\"p0\"]}/{hits[\"total\"]} ({100*hits[\"p0\"]//hits[\"total\"]}%)')
    print(f'  Phase 1 (Mem0):      {hits[\"p1\"]}/{hits[\"total\"]} ({100*hits[\"p1\"]//hits[\"total\"]}%)')
    print(f'  Phase 2 (FTS5):      {hits[\"p2\"]}/{hits[\"total\"]} ({100*hits[\"p2\"]//hits[\"total\"]}%)')
else:
    print('  (暂无召回数据)')
" 2>/dev/null
else
    echo "  (session-state.jsonl 不存在)"
fi
echo ""

# ── 5. Hook 管线状态 ──────────────────────
echo "【Hook 集成状态】"
MEMPL_HOOKS=$(grep -rl "mempalace\|chromadb" ~/.claude/hooks/ 2>/dev/null | wc -l | tr -d ' ')
TOTAL_HOOKS=$(ls ~/.claude/hooks/*.sh 2>/dev/null | wc -l | tr -d ' ')
echo "  MemPalace 集成: ${MEMPL_HOOKS} hooks"
echo "  总 Hook 数: ${TOTAL_HOOKS}"
echo ""

echo "========================================"
echo "  诊断完成"
echo "========================================"
