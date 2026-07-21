## 归档规则检索

活跃规则在 `~/.claude/solar/rules/`，历史铁律已归档并建立索引。需要时按以下方式检索：

```bash
# 方式1: Cortex 关键词搜索 (中文友好)
sqlite3 ~/.solar/db/solar.db "
SELECT citation_key, title, substr(finding,1,80)
FROM cortex_sources
WHERE task_id='rules-archive-indexing'
  AND (title LIKE '%关键词%' OR finding LIKE '%关键词%')
ORDER BY credibility DESC LIMIT 5;"

# 方式2: FTS 全文检索 (英文/标签)
sqlite3 ~/.solar/db/solar.db "
SELECT doc_id, title FROM fts_unified_search
WHERE fts_unified_search MATCH '关键词'
  AND doc_type='archived_rule'
ORDER BY rank LIMIT 5;"

# 方式3: 读取完整规则
cat ~/.solar/rules-archive/<citation_key>.md
```

**触发时机**: 遇到似曾相识的问题、需要历史教训、想找旧规则时

## 规则索引 (详见 ~/.claude/solar/rules/*.md)
- 00-core-laws.md / 01-three-core-laws.md - 核心操作法则
- state-persistence.md / state-machine-first.md - 状态持久化与状态机优先
- intent-engine.md - 统一意图引擎
- task-recommendation.md - 任务完成后的智能推荐
- task-create-protocol.md - TaskCreate 防颠倒协议 (3+步任务必须拆解)
- cortex-first.md - Cortex 优先
- no-mock.md / no-tmp-artifacts.md - 禁止 Mock 与临时产物
- constraint-verification.md / instruction-following.md - 约束验证与指令遵循
